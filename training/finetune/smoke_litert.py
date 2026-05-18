import litert_lm

def test_model(model_path, prompt="Write one sentence about the ocean."):
    with litert_lm.Engine(model_path=model_path, backend=litert_lm.Backend.CPU) as engine:
        with engine.create_session(apply_prompt_template=False) as session:
            formatted = f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
            session.run_prefill([formatted])
            r = session.run_decode()
            return r.texts[0].replace("<end_of_turn>", "").strip()

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "./training/output/litert_test/model.litertlm"
    prompt = sys.argv[2] if len(sys.argv) > 2 else "Write one sentence about the ocean."
    print(test_model(path, prompt))
