"""
Fine-tune Gemma 4 E2B for healthcare wayfinding using Unsloth + LoRA.

Designed to run on Google Colab (free T4, 15GB VRAM) or any CUDA machine.

Usage:
  python finetune.py --data output/03_scored/scored_TIMESTAMP.jsonl
  python finetune.py --data output/03_scored/scored_TIMESTAMP.jsonl --epochs 3 --lr 2e-4
  python finetune.py --data output/03_scored/scored_TIMESTAMP.jsonl --export-only gemma4_lora

Requirements (install before running):
  pip install unsloth trl datasets
"""

import argparse
import json


def load_dataset_from_jsonl(path: str):
    """Load JSONL into a HuggingFace Dataset preserving native role/content format.

    Gemma-4's chat template expects {"role": "...", "content": "..."} — passing
    ShareGPT's {"from": "...", "value": "..."} trips the "roles must alternate"
    check in the Jinja template.
    """
    from datasets import Dataset

    examples = []
    with open(path) as f:
        for line in f:
            row = json.loads(line)
            messages = row.get("messages", [])
            if not messages:
                continue
            examples.append({"messages": messages})

    print(f"Loaded {len(examples)} training examples")
    return Dataset.from_list(examples)


def main():
    parser = argparse.ArgumentParser(description="Fine-tune Gemma 4 E2B with Unsloth")
    parser.add_argument("--data", type=str, required=True, help="Path to scored JSONL file (pre-filtered by score.py)")
    parser.add_argument("--model", type=str, default="unsloth/gemma-4-E2B-it", help="Base model name")
    parser.add_argument("--max-seq-length", type=int, default=8192, help="Max sequence length")
    parser.add_argument("--lora-rank", type=int, default=8, help="LoRA rank (default: 8)")
    parser.add_argument("--epochs", type=int, default=1, help="Number of training epochs")
    parser.add_argument("--max-steps", type=int, default=None, help="Max training steps (overrides epochs)")
    parser.add_argument("--lr", type=float, default=2e-4, help="Learning rate")
    parser.add_argument("--batch-size", type=int, default=1, help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=4, help="Gradient accumulation steps")
    parser.add_argument("--output-dir", type=str, default="gemma4_lora", help="Output directory for LoRA adapter")
    parser.add_argument("--gguf", type=str, default=None, help="Export GGUF to this directory (e.g. gemma4_gguf)")
    parser.add_argument("--gguf-quant", type=str, default="q4_k_m", help="GGUF quantization method (default: q4_k_m)")
    parser.add_argument("--export-only", type=str, default=None, help="Skip training, load existing LoRA adapter and export")
    args = parser.parse_args()

    # ---------------------------------------------------------------
    # Step 1: Load model
    # ---------------------------------------------------------------
    from unsloth import FastModel

    if args.export_only:
        print(f"Loading existing LoRA adapter from {args.export_only}...")
        model, tokenizer = FastModel.from_pretrained(
            model_name=args.export_only,
            max_seq_length=args.max_seq_length,
            dtype=None,
            load_in_4bit=True,
        )
    else:
        print(f"Loading base model: {args.model}")
        model, tokenizer = FastModel.from_pretrained(
            model_name=args.model,
            max_seq_length=args.max_seq_length,
            dtype=None,
            load_in_4bit=True,
            full_finetuning=False,
        )

        # ---------------------------------------------------------------
        # Step 2: Attach LoRA adapters
        # ---------------------------------------------------------------
        print(f"Attaching LoRA adapters (rank={args.lora_rank})")
        model = FastModel.get_peft_model(
            model,
            finetune_vision_layers=False,
            finetune_language_layers=True,
            finetune_attention_modules=True,
            finetune_mlp_modules=True,
            r=args.lora_rank,
            lora_alpha=args.lora_rank,
            lora_dropout=0,
            bias="none",
            random_state=3407,
        )

        # ---------------------------------------------------------------
        # Step 3: Set chat template
        # ---------------------------------------------------------------
        from unsloth.chat_templates import get_chat_template

        tokenizer = get_chat_template(
            tokenizer,
            chat_template="gemma-4",
        )

        # ---------------------------------------------------------------
        # Step 4: Load and format dataset
        # ---------------------------------------------------------------
        dataset = load_dataset_from_jsonl(args.data)

        def formatting_prompts_func(examples):
            texts = [
                tokenizer.apply_chat_template(
                    msgs,
                    tokenize=False,
                    add_generation_prompt=False,
                ).removeprefix("<bos>")
                for msgs in examples["messages"]
            ]
            return {"text": texts}

        dataset = dataset.map(formatting_prompts_func, batched=True)
        print(f"Dataset formatted: {len(dataset)} examples")

        # ---------------------------------------------------------------
        # Step 5: Train
        # ---------------------------------------------------------------
        from trl import SFTTrainer, SFTConfig
        from unsloth.chat_templates import train_on_responses_only

        training_args = SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            warmup_steps=5,
            learning_rate=args.lr,
            logging_steps=1,
            optim="adamw_8bit",
            weight_decay=0.001,
            lr_scheduler_type="linear",
            seed=3407,
            output_dir=args.output_dir,
            report_to="none",
        )

        if args.max_steps:
            training_args.max_steps = args.max_steps
        else:
            training_args.num_train_epochs = args.epochs

        trainer = SFTTrainer(
            model=model,
            tokenizer=tokenizer,
            train_dataset=dataset,
            eval_dataset=None,
            args=training_args,
        )

        # Only train on assistant/model responses, not system/user turns
        trainer = train_on_responses_only(
            trainer,
            instruction_part="<|turn>user\n",
            response_part="<|turn>model\n",
        )

        print("Starting training...")
        stats = trainer.train()
        print(f"Training complete. Loss: {stats.training_loss:.4f}")

        # ---------------------------------------------------------------
        # Step 6: Save LoRA adapter
        # ---------------------------------------------------------------
        print(f"Saving LoRA adapter to {args.output_dir}/")
        model.save_pretrained(args.output_dir)
        tokenizer.save_pretrained(args.output_dir)

    # ---------------------------------------------------------------
    # Step 7: Export GGUF (optional)
    # ---------------------------------------------------------------
    if args.gguf:
        print(f"\nExporting GGUF ({args.gguf_quant}) to {args.gguf}/")
        model.save_pretrained_gguf(
            args.gguf,
            tokenizer,
            quantization_method=args.gguf_quant,
        )
        print(f"GGUF exported. To use in Ollama, create a Modelfile:")
        print(f"  FROM ./{args.gguf}/unsloth.{args.gguf_quant.upper()}.gguf")
        print(f"  Then: ollama create wayfinder -f Modelfile")


if __name__ == "__main__":
    main()
