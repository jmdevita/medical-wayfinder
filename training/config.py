"""
Shared configuration for the training data generation pipeline.

All scripts import from here. Change BASE_URL and MODEL to switch
between local (llama-swap, Ollama) and cloud (Claude, etc.) endpoints.

Environment variables:
  OPENAI_BASE_URL  — API endpoint (default: http://localhost:8080/v1)
  OPENAI_MODEL     — Model name (default: gemma-31b)
  OPENAI_API_KEY   — API key (default: not-needed for local)
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# --- Paths ---

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
SEEDS_FILE = DATA_DIR / "seeds" / "seeds.jsonl"
FACILITIES_DIR = DATA_DIR / "facilities"
PROMPTS_DIR = DATA_DIR / "prompts"
OUTPUT_DIR = ROOT / "output"
REJECTED_DIR = OUTPUT_DIR / "rejected"
EVAL_DIR = DATA_DIR / "eval"
EVAL_RESULTS_DIR = OUTPUT_DIR / "eval_results"

# --- API Configuration ---

BASE_URL = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
MODEL = os.environ.get("OPENAI_MODEL", "gemma4:e2b")
API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    os.environ.get("ANTHROPIC_API_KEY", "not-needed"),
)

# --- Generation Settings ---

BATCH_SIZE = 1          # Examples per API call
CONCURRENCY = 3         # Parallel requests (lower for local models)
TEMPERATURE = 0.8       # Higher = more diverse, lower = more consistent
SCORE_THRESHOLD = 3.5   # Minimum average score to keep (out of 5.0)

# --- Filler phrases to reject ---

FILLER_PHRASES = [
    # Generic AI tics
    "please feel free to ask",
    "I'd be happy to help",
    "don't hesitate to",
    "I'm here to help you",
    "as an AI",
    "I'm just a",
    "I'm an AI",
    "please let me know if",
    "of course!",
    "certainly!",
    "sure thing",
    "let me help",
    "got it!",
    "I understand",
    "great question",
    # Wayfinding anti-patterns: the patient is OUTSIDE the building looking
    # for help — telling them to find a desk or staff member is a failed
    # response. Phrases are intentionally specific so legitimate
    # `arrival.check_in` text ("Check in at the front desk") doesn't trip
    # the filter — we want to catch ADVICE to find a desk, not a check-in
    # location. These complement the `no_front_desk_punt` category by
    # rejecting at validate-time anything that slipped past the teacher.
    "go to the front desk",
    "head to the front desk",
    "head to reception",
    "ask at the front desk",
    "ask at reception",
    "ask reception",
    "check with reception",
    "check with staff",
    "ask a staff member",
    "ask someone inside",
    "find a sign",
    "look for a sign",
]


# --- Helpers ---

def ensure_dirs():
    """Create all output directories if they don't exist."""
    for subdir in ["01_raw", "02_validated", "03_scored", "04_final"]:
        (OUTPUT_DIR / subdir).mkdir(parents=True, exist_ok=True)
    REJECTED_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def get_client(base_url: str | None = None):
    """Return a configured AsyncOpenAI client."""
    from openai import AsyncOpenAI
    import httpx
    return AsyncOpenAI(
        base_url=base_url or BASE_URL,
        api_key=API_KEY,
        timeout=httpx.Timeout(600.0, connect=30.0),  # 10 min for slow/thinking models
    )


def load_system_prompt() -> str:
    """Load the system prompt template from file."""
    return (PROMPTS_DIR / "system_prompt.txt").read_text()


def load_generation_prompt() -> str:
    """Load the generation meta-prompt template from file."""
    return (PROMPTS_DIR / "generation.txt").read_text()


def load_facilities() -> dict[str, str]:
    """Load all facility JSON files. Returns {filename_stem: json_string}.
    Skips topology sidecars (`*.topology.json`) — those are loaded by
    `load_facility_topologies()`."""
    facilities = {}
    for f in FACILITIES_DIR.glob("*.json"):
        if f.name.endswith(".topology.json"):
            continue
        facilities[f.stem] = f.read_text()
    return facilities


def load_categories() -> dict[str, dict]:
    """Load the unified generation-categories config. Single source of truth
    for batch counts, teacher instructions, and phrase-bucket mapping per
    conversation category. Each value is a dict with keys:
      - batches (int): number of batches to generate (× BATCH_SIZE examples)
      - phrase_buckets (list[str]): which mined phrase categories to sample
      - instructions (str): per-category instructions for the teacher model
    """
    import json
    return json.loads((PROMPTS_DIR / "categories.json").read_text())


def load_scoring_rubric() -> str:
    """Load the scoring rubric template from file."""
    return (PROMPTS_DIR / "scoring_rubric.txt").read_text()


def load_eval_rubric() -> str:
    """Load the eval rubric template from file (used by eval_runner)."""
    return (PROMPTS_DIR / "eval_rubric.txt").read_text()


def load_criteria() -> dict:
    """Load the unified scoring-criteria config. Single source of truth for
    the criterion list shared by score.py and eval_runner.py."""
    import json
    return json.loads((PROMPTS_DIR / "criteria.json").read_text())


def build_criteria_block(cfg: dict) -> str:
    """Render the criteria list as numbered prose for inclusion in a rubric."""
    lines = []
    for i, c in enumerate(cfg["criteria"], start=1):
        lines.append(f"{i}. {c['label']}: {c['description']}")
        if c.get("scale"):
            lines.append(f"   {c['scale']}")
        lines.append("")
    return "\n".join(lines).rstrip()


def build_criteria_schema(cfg: dict) -> dict:
    """Build the OpenAI response_format schema dict from the criteria config."""
    properties = {c["key"]: {"type": "integer"} for c in cfg["criteria"]}
    properties[cfg["notes_field"]] = {"type": "string"}
    required = [c["key"] for c in cfg["criteria"]] + [cfg["notes_field"]]
    return {
        "type": "json_schema",
        "json_schema": {
            "name": cfg.get("name", "criteria_score"),
            "strict": True,
            "schema": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


def render_rubric(rubric_template: str, cfg: dict) -> str:
    """Substitute the {criteria_block} placeholder in a rubric template.
    Uses str.replace to avoid conflicts with per-example {...} placeholders
    that the caller will fill via .format() afterwards."""
    return rubric_template.replace("{criteria_block}", build_criteria_block(cfg))


def load_facilities_parsed() -> dict[str, dict]:
    """Load all facility JSON files as parsed dicts. Returns {stem: dict}.

    Skips topology sidecars (`*.topology.json`) — those are loaded
    separately by `load_facility_topologies`.
    """
    import json
    return {
        f.stem: json.loads(f.read_text())
        for f in FACILITIES_DIR.glob("*.json")
        if not f.name.endswith(".topology.json")
    }


def load_facility_topologies() -> dict[str, dict]:
    """Load all `*.topology.json` files as parsed dicts.

    Returns:
        Dict keyed by file stem (without `.topology` suffix), e.g.
        `kaiser_panorama_city` -> parsed topology dict. Stems match the
        keys returned by `load_facilities_parsed()` so callers can join
        the two by stem.
    """
    import json
    out: dict[str, dict] = {}
    for f in FACILITIES_DIR.glob("*.topology.json"):
        # f.stem on "kaiser.topology.json" gives "kaiser.topology" — strip it.
        stem = f.name.removesuffix(".topology.json")
        out[stem] = json.loads(f.read_text())
    return out


def _topology_find_route(topology: dict, from_id: str, to_id: str) -> list[dict]:
    """Bidirectional Dijkstra over a parsed topology dict.

    Mirrors the Dart implementation in `wayfinding_tools.dart`: edges are
    treated as undirected, reversed traversals get a synthesized
    "Head back toward …" instruction. Returns a list of dicts shaped like
    `{"from_label": str, "to_label": str, "instruction": str}`.
    Returns [] when no path exists or either node is unknown.
    """
    nodes = {n["id"]: n for n in topology.get("nodes", [])}
    if from_id not in nodes or to_id not in nodes or from_id == to_id:
        return []

    # Undirected adjacency: each entry is (neighbor_id, edge, reversed, cost).
    # Cost is computed once into the tuple so the input topology dict is
    # never mutated.
    adj: dict[str, list[tuple[str, dict, bool, float]]] = {}
    for e in topology.get("edges", []):
        if e.get("blocked"):
            continue
        cost = e.get("distance_meters", 0) or e.get("walk_minutes", 0) * 80
        adj.setdefault(e["from"], []).append((e["to"], e, False, cost))
        adj.setdefault(e["to"], []).append((e["from"], e, True, cost))

    import heapq
    dist = {from_id: 0.0}
    prev: dict[str, tuple[str, dict, bool]] = {}
    pq = [(0.0, from_id)]
    visited: set[str] = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        if u == to_id:
            break
        for v, edge, reversed_, cost in adj.get(u, []):
            cand = d + cost
            if cand < dist.get(v, float("inf")):
                dist[v] = cand
                prev[v] = (u, edge, reversed_)
                heapq.heappush(pq, (cand, v))

    if to_id not in prev:
        return []

    steps_rev: list[dict] = []
    cursor = to_id
    while cursor != from_id:
        u, edge, reversed_ = prev[cursor]
        from_node = nodes[u]
        to_node = nodes[cursor]
        instruction = (
            f"Head back toward {to_node['label']}."
            if reversed_
            else edge.get("instruction", "")
        )
        steps_rev.append({
            "from_label": from_node["label"],
            "to_label": to_node["label"],
            "instruction": instruction,
        })
        cursor = u
    return list(reversed(steps_rev))


def _default_origin_node(topology: dict, dept: dict, facility: dict) -> str | None:
    """Pick the parking node that serves the department's building.

    Falls back to any parking node when no parking area lists the building.
    """
    nodes = topology.get("nodes", [])
    target_building = (dept.get("building") or "").lower()

    # Find the parking area whose nearest_buildings contains the target.
    candidate_areas = [
        area for area in facility.get("parking", [])
        if any(b.lower() == target_building for b in area.get("nearest_buildings", []))
    ]

    parking_nodes = [n for n in nodes if n.get("type") == "parking"]
    for area in candidate_areas:
        area_lower = area["name"].lower()
        for n in parking_nodes:
            label_lower = n["label"].lower()
            if label_lower in area_lower or area_lower.split(" ")[0] in label_lower:
                return n["id"]

    return parking_nodes[0]["id"] if parking_nodes else None


def _destination_node_for(topology: dict, dept: dict) -> str | None:
    """Resolve a department to a topology node id.

    Prefers an explicit `topology_node_id` on the dept record so that
    distinct departments in the same building (e.g. ER vs Radiology
    both in "Hospital") route to different entrances. Falls back to
    matching `dept.building` against entrance-type node labels.
    """
    explicit = dept.get("topology_node_id")
    if explicit:
        for n in topology.get("nodes", []):
            if n["id"] == explicit:
                return explicit

    target = (dept.get("building") or "").lower()
    entrance_nodes = [n for n in topology.get("nodes", []) if n.get("type") == "entrance"]
    for n in entrance_nodes:
        if n["label"].lower() == target:
            return n["id"]
    for n in entrance_nodes:
        if target in n["label"].lower():
            return n["id"]
    return None


def build_context_block(facility: dict, department_name: str | None = None,
                        candidates: list[str] | None = None,
                        topology: dict | None = None) -> str:
    """Build a compact CONTEXT block matching the Flutter orchestrator output.

    Args:
        facility: Parsed facility JSON dict.
        department_name: Target department name for a resolved lookup.
        candidates: List of department names for a disambiguation case.
        topology: Optional parsed topology dict. When provided, the block
            includes a `Route from <origin>:` section instead of the
            single `Directions:` line.

    Returns:
        Plain-text CONTEXT block (~200-400 tokens).
    """
    lines = [f"Facility: {facility['name']}"]

    if candidates:
        lines.append("Candidates:")
        for dept in facility.get("departments", []):
            if dept["name"] in candidates:
                lines.append(f"- {dept['name']}, {dept['building']}, {dept['floor']}")
        return "\n".join(lines)

    if department_name:
        dept = None
        for d in facility.get("departments", []):
            if d["name"] == department_name:
                dept = d
                break
        if dept is None:
            # Fuzzy match: check if department_name is a substring
            for d in facility.get("departments", []):
                if department_name.lower() in d["name"].lower():
                    dept = d
                    break

        if dept:
            lines.append(f"Department: {dept['name']}")
            lines.append(f"Building: {dept['building']}")
            lines.append(f"Floor: {dept['floor']}")
            if dept.get("hours"):
                lines.append(f"Hours: {dept['hours']}")
            if dept.get("check_in"):
                lines.append(f"Check-in: {dept['check_in']}")
            lines.append(f"Accessible: {'Yes' if dept.get('accessible', True) else 'No'}")

            route_steps: list[dict] = []
            if topology is not None:
                origin = _default_origin_node(topology, dept, facility)
                dest = _destination_node_for(topology, dept)
                if origin and dest:
                    route_steps = _topology_find_route(topology, origin, dest)

            directions = (dept.get("directions")
                          or dept.get("directions_from_cantara")
                          or dept.get("directions_from_ventura")
                          or "")

            if route_steps:
                lines.append(f"Route from {route_steps[0]['from_label']}:")
                for i, step in enumerate(route_steps, 1):
                    lines.append(f"  {i}. {step['instruction']}")
            elif directions:
                lines.append(f"Directions: {directions}")

            # Extract accessibility features from directions and route text.
            blob_parts = [directions]
            blob_parts.extend(s["instruction"] for s in route_steps)
            blob = " ".join(blob_parts).lower()
            features = []
            if "elevator" in blob:
                features.append("elevator")
            if "ramp" in blob:
                features.append("ramp")
            if "automatic door" in blob:
                features.append("automatic_doors")
            if "accessible entrance" in blob or "accessible)" in blob:
                features.append("accessible_entrance")
            if features:
                lines.append(f"Accessibility features: {', '.join(features)}")

    return "\n".join(lines)


def build_reorientation_context_block(facility: dict, department_name: str,
                                      current_node_id: str,
                                      topology: dict) -> str:
    """Build a CONTEXT block for a re-orientation example.

    Args:
        facility: Parsed facility JSON dict.
        department_name: Standing destination's name.
        current_node_id: ID of the topology node where the patient is now.
        topology: Parsed topology dict for this facility.

    Returns:
        Plain-text block: facility, department, current location, route to dest.
    """
    dept = None
    for d in facility.get("departments", []):
        if d["name"] == department_name or department_name.lower() in d["name"].lower():
            dept = d
            break
    if dept is None:
        return f"Facility: {facility['name']}\nDepartment: {department_name}"

    nodes = {n["id"]: n for n in topology.get("nodes", [])}
    located = nodes.get(current_node_id)
    if located is None:
        return build_context_block(facility, department_name, topology=topology)

    dest = _destination_node_for(topology, dept)
    route = (
        _topology_find_route(topology, current_node_id, dest)
        if dest
        else []
    )

    lines = [
        f"Facility: {facility['name']}",
        f"Department: {dept['name']} ({dept['building']})",
        f"Current location: {located['label']}",
        "Route to destination:",
    ]
    for i, step in enumerate(route, 1):
        lines.append(f"  {i}. {step['instruction']}")
    if dept.get("check_in"):
        lines.append(f"Check-in: {dept['check_in']}")
    return "\n".join(lines)


def load_seeds() -> list[dict]:
    """Load seed examples from JSONL file."""
    import json
    seeds = []
    with open(SEEDS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                seeds.append(json.loads(line))
    return seeds
