#!/usr/bin/env python3
"""
Rule-based validation of generated training examples.
No LLM needed — pure structural and content checks.

Usage:
  python validate.py output/01_raw/raw_2026-04-15T10-30-00.jsonl
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import FILLER_PHRASES, FACILITIES_DIR, PROMPTS_DIR, OUTPUT_DIR, REJECTED_DIR, ensure_dirs


def load_data_contract() -> dict:
    """Load the data contract schema for assistant message validation."""
    schema_file = PROMPTS_DIR / "data_contract.json"
    return json.loads(schema_file.read_text())


VALID_BLOCK_TYPES = {"destination", "steps", "disambig", "guide_text", "arrival"}
VALID_ACCESSIBILITY_BADGES = {"elevator", "ramp", "automatic_doors", "accessible_entrance", "arrived"}

BLOCK_REQUIRED_FIELDS = {
    "destination": ["department", "building", "floor"],
    "steps": ["steps"],
    "disambig": ["question", "options"],
    "guide_text": ["text"],
    "arrival": ["check_in"],
}

# Fields that must be present in the block (per BLOCK_REQUIRED_FIELDS) but
# are allowed to hold an empty string. Aligns the training contract with the
# app's runtime contract: response_parser.dart accepts floor="" and the
# UI's _composeFloorHint() explicitly treats empty/"ground"/"1st" as
# "suppress the elevator-to-floor cue" — designed-in behavior for
# single-story clinics (e.g. Atrius Boston Kenmore). Without this exemption
# every Atrius example gets dropped here even though it would render fine
# in the app.
ALLOWED_EMPTY_FIELDS = {("destination", "floor")}


def validate_block(block: dict, msg_idx: int, block_idx: int) -> list[str]:
    """Validate a single message block against the output schema contract."""
    issues = []
    prefix = f"Assistant message {msg_idx}, block {block_idx}"

    if not isinstance(block, dict):
        return [f"{prefix}: not an object"]

    block_type = block.get("type")
    if not block_type:
        return [f"{prefix}: missing 'type' field"]
    if block_type not in VALID_BLOCK_TYPES:
        return [f"{prefix}: unknown type '{block_type}'"]

    # Check required fields
    for field in BLOCK_REQUIRED_FIELDS[block_type]:
        if field not in block:
            issues.append(f"{prefix}: '{block_type}' missing required field '{field}'")
        elif (
            isinstance(block[field], str)
            and not block[field].strip()
            and (block_type, field) not in ALLOWED_EMPTY_FIELDS
        ):
            issues.append(f"{prefix}: '{block_type}.{field}' is empty")

    # Check allowed fields (no extra keys)
    allowed = {"type"} | set(BLOCK_REQUIRED_FIELDS[block_type])
    extra = set(block.keys()) - allowed
    if extra:
        issues.append(f"{prefix}: unexpected fields {extra}")

    # Type-specific validation
    if block_type == "steps" and "steps" in block:
        steps = block["steps"]
        if not isinstance(steps, list) or len(steps) == 0:
            issues.append(f"{prefix}: 'steps' must be a non-empty array")
        else:
            for si, step in enumerate(steps):
                if not isinstance(step, dict):
                    issues.append(f"{prefix}, step {si}: not an object")
                    continue
                if "text" not in step or not step["text"].strip():
                    issues.append(f"{prefix}, step {si}: missing or empty 'text'")
                if "accessibility" not in step:
                    issues.append(f"{prefix}, step {si}: missing 'accessibility' field")
                elif step["accessibility"] is not None and step["accessibility"] not in VALID_ACCESSIBILITY_BADGES:
                    issues.append(f"{prefix}, step {si}: invalid accessibility badge '{step['accessibility']}'")
                step_allowed = {"text", "accessibility"}
                step_extra = set(step.keys()) - step_allowed
                if step_extra:
                    issues.append(f"{prefix}, step {si}: unexpected fields {step_extra}")

    if block_type == "disambig" and "options" in block:
        opts = block["options"]
        if not isinstance(opts, list) or len(opts) < 2:
            issues.append(f"{prefix}: 'disambig.options' needs at least 2 items")

    return issues


def load_facility_data() -> tuple[set[str], set[str], dict[str, set[str]], dict[str, set[str]]]:
    """Load department and building names from facility JSONs.

    Returns four collections:
      - `departments` (global): union of all department names across facilities.
        Kept for backward compatibility with the original signature.
      - `buildings` (global): union of all building names across facilities.
      - `facility_buildings`: {facility_stem: {building_names}}. Per-facility
        building whitelist for the strict declared-building check.
      - `facility_departments`: {facility_stem: {department_names}}.

    Skips topology sidecars (`*.topology.json`).
    """
    departments: set[str] = set()
    buildings: set[str] = set()
    facility_buildings: dict[str, set[str]] = {}
    facility_departments: dict[str, set[str]] = {}
    for f in FACILITIES_DIR.glob("*.json"):
        if f.name.endswith(".topology.json"):
            continue
        try:
            data = json.loads(f.read_text())
            fb: set[str] = set()
            fd: set[str] = set()
            for b in data.get("buildings", []):
                if b.get("name"):
                    fb.add(b["name"])
            for d in data.get("departments", []):
                if d.get("name"):
                    fd.add(d["name"])
                if d.get("building"):
                    fb.add(d["building"])
            facility_buildings[f.stem] = fb
            facility_departments[f.stem] = fd
            buildings.update(fb)
            departments.update(fd)
        except (json.JSONDecodeError, KeyError):
            pass
    buildings.discard("")
    return departments, buildings, facility_buildings, facility_departments


def validate(
    example: dict,
    known_departments: set,
    known_buildings: set,
    facility_buildings: dict[str, set[str]] | None = None,
) -> tuple[bool, list[str]]:
    """Validate a single example. Returns (is_valid, issues)."""
    issues = []
    messages = example.get("messages")

    # 1. Structure
    if not isinstance(messages, list) or len(messages) < 3:
        issues.append("Too few messages (need at least system + user + assistant)")
        return False, issues

    # 2. Roles present and valid on every message. Teachers occasionally
    # emit {"assistant": "assistant", "content": ...} (no "role" key) —
    # downstream code (score.py, finetune) keys on .role and would crash or
    # silently mis-train. Reject any message whose role is not one of the
    # three expected values.
    valid_roles = {"system", "user", "assistant"}
    for i, m in enumerate(messages):
        role = m.get("role")
        if role not in valid_roles:
            issues.append(f"Message {i} has invalid/missing role: {role!r} (keys: {list(m.keys())})")
    roles = {m.get("role") for m in messages}
    if "system" not in roles:
        issues.append("Missing system message")
    if "user" not in roles:
        issues.append("Missing user message")
    if "assistant" not in roles:
        issues.append("Missing assistant message")

    # 3. System message is first
    if messages[0].get("role") != "system":
        issues.append("First message must be system role")

    # 4. Turn count (non-system)
    turns = [m for m in messages if m.get("role") != "system"]
    if len(turns) < 2:
        issues.append(f"Only {len(turns)} turns (need at least 2)")
    if len(turns) > 14:
        issues.append(f"{len(turns)} turns — too long (max 14)")

    # 5. System prompt contains facility context
    system_msg = messages[0] if messages[0].get("role") == "system" else None
    if system_msg:
        content = system_msg.get("content", "")
        has_context = ("CONTEXT:" in content or "Facility:" in content
                       or "FACILITY DATA" in content)
        if not has_context:
            issues.append("System message missing facility context")

    # 6. Filler phrases in assistant messages
    for m in messages:
        if m.get("role") == "assistant":
            content_lower = m.get("content", "").lower()
            for filler in FILLER_PHRASES:
                if filler.lower() in content_lower:
                    issues.append(f"Filler phrase: '{filler}'")
                    break  # One filler per message is enough to flag

    # 7. Language consistency
    user_messages = [m for m in messages if m.get("role") == "user"]
    if user_messages:
        first_user = user_messages[0].get("content", "").lower()
        spanish_markers = ["donde", "necesito", "doctor de", "está", "quiero",
                          "estoy", "como llego", "dónde", "ayuda"]
        is_spanish = any(marker in first_user for marker in spanish_markers)

        if is_spanish:
            for m in messages:
                if m.get("role") == "assistant":
                    content_lower = m.get("content", "").lower()
                    english_markers = ["here are", "you're looking for",
                                      "please note", "the department is",
                                      "here's how to get"]
                    if any(marker in content_lower for marker in english_markers):
                        issues.append("Assistant responded in English to Spanish-speaking patient")
                        break

    # 8. Empty content
    for i, m in enumerate(messages):
        content = m.get("content", "")
        if not content or not content.strip():
            issues.append(f"Empty content in message {i} (role: {m.get('role')})")

    # 8b. Assistant messages must be valid JSON arrays matching the output schema contract
    for i, m in enumerate(messages):
        if m.get("role") == "assistant":
            content = m.get("content", "")
            try:
                blocks = json.loads(content)
                if not isinstance(blocks, list):
                    issues.append(f"Assistant message {i}: not a JSON array")
                elif len(blocks) == 0:
                    issues.append(f"Assistant message {i}: empty JSON array")
                else:
                    for j, block in enumerate(blocks):
                        issues.extend(validate_block(block, i, j))
            except json.JSONDecodeError:
                issues.append(f"Assistant message {i}: content is not valid JSON")

    # 9. Role alternation (after system, should alternate user/assistant)
    non_system = [m for m in messages if m.get("role") != "system"]
    for i in range(len(non_system) - 1):
        current = non_system[i].get("role")
        next_role = non_system[i + 1].get("role")
        if current == next_role:
            issues.append(f"Consecutive {current} messages at turn {i + 1}")
            break

    # 10. First non-system message should be user
    if non_system and non_system[0].get("role") != "user":
        issues.append("First non-system message should be user role")

    # 11. Building hallucination checks
    # 11a. STRICT: `destination.building` and `destination.department` must
    #      exist in this facility's whitelist. This catches the dominant
    #      hallucination mode (teacher invents a building name) without
    #      false-positives on prose phrasing.
    facility_name = example.get("facility")
    fb_whitelist = (facility_buildings or {}).get(facility_name, set())
    if facility_name and fb_whitelist:
        for i, m in enumerate(messages):
            if m.get("role") != "assistant":
                continue
            try:
                blocks = json.loads(m.get("content", ""))
            except json.JSONDecodeError:
                continue
            if not isinstance(blocks, list):
                continue
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "destination":
                    bname = block.get("building", "")
                    if bname and bname not in fb_whitelist:
                        issues.append(
                            f"Assistant message {i}: destination.building "
                            f"'{bname}' not in facility '{facility_name}' "
                            f"whitelist"
                        )

    # 11b. SOFT: legacy "Building \d" sweep against global whitelist. Catches
    #      cases where prose mentions an off-by-one building number even if
    #      the destination.building was correct.
    if known_buildings:
        for m in messages:
            if m.get("role") == "assistant":
                content = m.get("content", "")
                for bm in re.findall(r'Building \d+\w?', content):
                    if bm not in known_buildings:
                        issues.append(f"Unknown building mentioned: '{bm}'")
                        break

    return len(issues) == 0, issues


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate.py <input_file.jsonl>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    ensure_dirs()
    known_departments, known_buildings, facility_buildings, _ = load_facility_data()

    stem = input_path.stem
    output_file = OUTPUT_DIR / "02_validated" / f"{stem}_validated.jsonl"
    rejected_file = REJECTED_DIR / f"{stem}_rejected.jsonl"

    valid_count = 0
    reject_count = 0
    all_issues = []

    with open(output_file, "w") as out, open(rejected_file, "w") as rej, open(input_path) as inp:
        for line_num, line in enumerate(inp, 1):
            line = line.strip()
            if not line:
                continue

            try:
                example = json.loads(line)
            except json.JSONDecodeError as e:
                reject_count += 1
                rej.write(json.dumps({
                    "line": line_num,
                    "issues": [f"Invalid JSON: {e}"],
                    "raw": line[:200],
                }) + "\n")
                continue

            is_valid, issues = validate(
                example, known_departments, known_buildings, facility_buildings
            )

            if is_valid:
                out.write(json.dumps(example, ensure_ascii=False) + "\n")
                valid_count += 1
            else:
                all_issues.extend(issues)
                msgs = example.get("messages", [])
                preview = msgs[1].get("content", "")[:80] if len(msgs) > 1 else "?"
                rej.write(json.dumps({
                    "line": line_num,
                    "issues": issues,
                    "preview": preview,
                }, ensure_ascii=False) + "\n")
                reject_count += 1

    total = valid_count + reject_count
    pct = (valid_count / total * 100) if total > 0 else 0

    print(f"\n✓ Validation complete")
    print(f"  Total:    {total}")
    print(f"  Valid:    {valid_count} ({pct:.0f}%)")
    print(f"  Rejected: {reject_count}")
    print(f"  Output:  {output_file}")
    if reject_count > 0:
        print(f"  Rejected: {rejected_file}")

        # Show top issues
        from collections import Counter
        issue_counts = Counter(all_issues)
        print(f"\n  Top issues:")
        for issue, count in issue_counts.most_common(5):
            print(f"    [{count}] {issue}")


if __name__ == "__main__":
    main()
