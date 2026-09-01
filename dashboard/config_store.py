"""
Versioned config storage for the OLX Negotiation Copilot dashboard.

Every "deploy" from the Play/Tweak page creates a NEW version here — nothing
is ever overwritten. v1.0 is seeded from the real prompt text in
app/agent.py (the actual working agent, not a placeholder), so the very
first version in this store is exactly what's already running.

Storage is a plain JSON file (dashboard/data/versions.json) — no DB server
needed for something this small, and it's easy for you to read/diff by hand.
"""
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Optional

DASHBOARD_DIR = Path(__file__).resolve().parent
ROOT = DASHBOARD_DIR.parent
DATA_DIR = DASHBOARD_DIR / "data"
VERSIONS_PATH = DATA_DIR / "versions.json"

sys.path.insert(0, str(ROOT / "app"))
import agent as base_agent  # noqa: E402  (the real, working agent module)

# Models actually verified working end-to-end for this project (see README.md
# "Reliability notes"). Don't offer models that were never confirmed to work
# on this Groq account.
AVAILABLE_MODELS = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]

PROMPT_KEYS = [
    "research_tool_instructions",
    "research_parser_instructions",
    "strategy_instructions",
    "negotiation_instructions",
    "final_instructions",
]


def _v1_prompts() -> dict:
    """Pull the ACTUAL instruction text out of the live agent module, not a
    rewritten copy — so v1.0 in this store is provably identical to what
    app/agent.py runs today."""
    return {
        "research_tool_instructions": "\n\n".join(
            i for i in base_agent._make_research_tool_agent().instructions
        ),
        "research_parser_instructions": "\n\n".join(
            i for i in base_agent._make_research_parser_agent().instructions
        ),
        "strategy_instructions": "\n\n".join(
            i for i in base_agent._make_strategy_agent().instructions
        ),
        "negotiation_instructions": "\n\n".join(
            i for i in base_agent._make_negotiation_agent().instructions
        ),
        "final_instructions": "\n\n".join(
            i for i in base_agent._make_final_agent().instructions
        ),
    }


def _seed() -> dict:
    v1_id = "v1.0"
    v1 = {
        "id": v1_id,
        "label": "v1.0 — baseline (as shipped)",
        "created_at": time.time(),
        "model_id": base_agent.GROQ_MODEL_ID,
        "temperature": base_agent.TEMPERATURE,
        "prompts": _v1_prompts(),
        "notes": "Seeded automatically from app/agent.py's real prompt text — this is the exact agent that was eval-scored in evals/EVAL_SCORECARD.md.",
    }
    return {"versions": {v1_id: v1}, "active_version_id": v1_id}


def _load_raw() -> dict:
    if not VERSIONS_PATH.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = _seed()
        VERSIONS_PATH.write_text(json.dumps(data, indent=2))
        return data
    return json.loads(VERSIONS_PATH.read_text())


def _save_raw(data: dict) -> None:
    VERSIONS_PATH.write_text(json.dumps(data, indent=2))


def list_versions() -> list:
    data = _load_raw()
    return sorted(data["versions"].values(), key=lambda v: v["created_at"])


def get_version(version_id: str) -> Optional[dict]:
    data = _load_raw()
    return data["versions"].get(version_id)


def get_active_version_id() -> str:
    return _load_raw()["active_version_id"]


def get_active_version() -> dict:
    data = _load_raw()
    return data["versions"][data["active_version_id"]]


def set_active_version(version_id: str) -> None:
    data = _load_raw()
    if version_id not in data["versions"]:
        raise KeyError(version_id)
    data["active_version_id"] = version_id
    _save_raw(data)


def create_version(
    label: str,
    model_id: str,
    temperature: float,
    prompts: dict,
    notes: str = "",
    make_active: bool = True,
) -> dict:
    """Creates a new, immutable version. Never edits an existing one."""
    data = _load_raw()
    existing_versions = [v for v in data["versions"].values()]
    next_n = len(existing_versions) + 1
    version_id = f"v1.{next_n - 1}-{uuid.uuid4().hex[:6]}" if next_n > 1 else "v1.0"
    # v1.0 always exists already (seeded), so any create_version call makes v1.N
    major_minor = f"v1.{next_n - 1}"
    version_id = f"{major_minor}-{uuid.uuid4().hex[:6]}"

    missing = [k for k in PROMPT_KEYS if k not in prompts]
    if missing:
        raise ValueError(f"create_version missing prompt keys: {missing}")

    new_version = {
        "id": version_id,
        "label": label or version_id,
        "created_at": time.time(),
        "model_id": model_id,
        "temperature": temperature,
        "prompts": prompts,
        "notes": notes,
    }
    data["versions"][version_id] = new_version
    if make_active:
        data["active_version_id"] = version_id
    _save_raw(data)
    return new_version
