"""
Deterministic eval checks that complement the LLM-as-judge in eval_runner.py.

These run cheaply and locally (no API calls) on every model response, so they
can be a CI gate even when the judge endpoint is offline. Three checks today:

  1. JSON parse-rate           — does the response decode as the data contract?
  2. Verbatim route fidelity   — when CONTEXT has "Route from X:" with numbered
                                  lines, do the model's steps[] copy those
                                  lines verbatim (case 1 of the system prompt)?
  3. Per-language reporting    — split the aggregate score by EN vs ES so the
                                  multilingual gap is tracked, not averaged
                                  into the headline.
"""

from __future__ import annotations

import json
import re
from typing import Any

# Markdown fences the model occasionally wraps the JSON in. We strip these
# before parsing so a fenced-but-otherwise-valid response still counts as a
# parse hit.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n?|\n?\s*```\s*$", re.MULTILINE)

# "Route from <label>:\n  1. ...\n  2. ..." — produced by build_context_block
# in config.py. The N. prefix is two-space indented; we tolerate any leading
# whitespace.
_ROUTE_HEADER_RE = re.compile(r"^Route from .+?:\s*$", re.MULTILINE)
_ROUTE_LINE_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s*$", re.MULTILINE)

# Lightweight Spanish detector — anchored to characters/words that would not
# appear in any English wayfinding query the eval set ships. Imperfect, but
# good enough to split the corpus in half for reporting.
_SPANISH_TOKENS = {
    "dónde", "donde", "está", "esta", "necesito", "tengo", "puedo",
    "ayuda", "hijo", "hija", "doctor", "doctora", "cita", "consulta",
    "farmacia", "emergencia", "urgencias", "sala", "edificio", "piso",
    "para", "porque", "buenos", "días", "noches", "dias",
}
_SPANISH_CHARS = set("¿¡ñáéíóúü")


def strip_fences(text: str) -> str:
    """Remove leading ```json / trailing ``` if present."""
    return _FENCE_RE.sub("", text).strip()


def parse_json_response(text: str) -> list[dict[str, Any]] | None:
    """Best-effort JSON parse of the model's response to the data contract.

    Returns the parsed list of blocks on success, None on failure. Mirrors
    what the Flutter ResponseParser sees: if json.loads fails, no fallback —
    we want to count this as a parse failure, not silently repair it.
    """
    if not text:
        return None
    cleaned = strip_fences(text)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    # Contract: top-level is a list of block dicts.
    if not isinstance(parsed, list):
        return None
    if not all(isinstance(b, dict) for b in parsed):
        return None
    return parsed


def extract_route_steps(system_prompt: str) -> list[str]:
    """Pull the numbered lines under a 'Route from X:' header in CONTEXT.

    Returns [] when no such block exists (case 1 wasn't pre-routed for this
    eval — verbatim check is N/A and should be skipped).
    """
    if not _ROUTE_HEADER_RE.search(system_prompt):
        return []
    # The header may appear once; we collect every numbered line that follows
    # it within the CONTEXT block. Heuristic: take the first contiguous run of
    # numbered lines after the header.
    header_match = _ROUTE_HEADER_RE.search(system_prompt)
    if header_match is None:
        return []
    tail = system_prompt[header_match.end():]
    # Stop at first blank-line gap.
    chunk = tail.split("\n\n", 1)[0]
    return [m.group(1).strip() for m in _ROUTE_LINE_RE.finditer(chunk)]


def check_verbatim_steps(
    parsed: list[dict[str, Any]] | None,
    route_steps: list[str],
) -> dict[str, Any]:
    """Verify each emitted steps[].text exists verbatim in route_steps.

    Returns:
        {
          "applicable": bool,           # was there a Route block to match?
          "matched": int,
          "expected": int,              # len(route_steps)
          "ok": bool,                   # all expected lines accounted for
          "missing": list[str],         # route lines the model didn't copy
        }
    """
    if not route_steps:
        return {"applicable": False, "matched": 0, "expected": 0, "ok": True, "missing": []}
    if parsed is None:
        return {
            "applicable": True, "matched": 0, "expected": len(route_steps),
            "ok": False, "missing": list(route_steps),
        }
    # Find the first steps block and check its text/instruction fields.
    step_texts: list[str] = []
    for block in parsed:
        if block.get("type") == "steps" and isinstance(block.get("steps"), list):
            for s in block["steps"]:
                if isinstance(s, dict):
                    text = s.get("text") or s.get("instruction")
                    if isinstance(text, str):
                        step_texts.append(text.strip())
            break  # first steps block only
    expected_set = {s.strip() for s in route_steps}
    matched = sum(1 for t in step_texts if t in expected_set)
    missing = [s for s in route_steps if s.strip() not in {t for t in step_texts}]
    return {
        "applicable": True,
        "matched": matched,
        "expected": len(route_steps),
        "ok": matched == len(route_steps) and not missing,
        "missing": missing,
    }


def detect_language(user_message: str) -> str:
    """Return 'es' if the message reads as Spanish, 'en' otherwise.

    Heuristic: any Spanish-only character (¿¡ñáéíóúü) wins immediately;
    otherwise, count Spanish tokens vs the message length. Conservative —
    English wayfinding queries shouldn't trip false positives.
    """
    if not user_message:
        return "en"
    if any(ch in _SPANISH_CHARS for ch in user_message):
        return "es"
    tokens = re.findall(r"\w+", user_message.lower())
    if not tokens:
        return "en"
    spanish_hits = sum(1 for t in tokens if t in _SPANISH_TOKENS)
    return "es" if spanish_hits >= 2 or (spanish_hits >= 1 and len(tokens) <= 4) else "en"


def deterministic_checks(
    response: str,
    system_prompt: str,
    user_message: str,
) -> dict[str, Any]:
    """Run all deterministic checks against a single (response, prompt) pair."""
    parsed = parse_json_response(response)
    json_ok = parsed is not None
    route = extract_route_steps(system_prompt)
    verbatim = check_verbatim_steps(parsed, route)
    return {
        "json_ok": json_ok,
        "verbatim": verbatim,
        "language": detect_language(user_message),
    }
