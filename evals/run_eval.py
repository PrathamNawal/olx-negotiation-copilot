"""
Phase 4 eval harness — runs the REAL agent pipeline (Groq + Serper, no
mocking) against the TEST_CASES library and records what actually happened.

This produces evals/eval_results.json, which EVAL_SCORECARD.md's Section 2/3
scores are read from, and (if MLflow is available) logs one MLflow run per
test case so results are comparable across future prompt/model versions.

Usage:
    cd evals && python3 run_eval.py
"""
import json
import os
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

# Load .env manually (no extra dependency).
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from agent import (  # noqa: E402
    run_research,
    run_strategy,
    run_negotiation_move,
    run_final_outcome,
    GROQ_MODEL_ID,
)
from test_cases import TEST_CASES  # noqa: E402

try:
    import mlflow

    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


def money(v):
    return f"₹{v:,.0f}" if v is not None else "—"


def run_one(tc: dict) -> dict:
    result = {
        "id": tc["id"],
        "label": tc["label"],
        "listing_text": tc["listing_text"],
        "budget": tc["budget"],
        "urgency": tc["urgency"],
        "dealbreakers": tc["dealbreakers"],
        "error_stage": None,
        "error_message": None,
    }
    t_start = time.time()

    # --- Phase 1: research ---
    try:
        research = run_research(tc["listing_text"])
    except Exception as e:
        result["error_stage"] = "research"
        result["error_message"] = str(e)
        result["duration_sec"] = round(time.time() - t_start, 1)
        return result

    result["asking_price"] = research.asking_price
    result["fair_price_low"] = research.fair_price_low
    result["fair_price_high"] = research.fair_price_high
    result["confidence_note"] = research.confidence_note
    result["comps_count"] = len(research.comps)
    result["comps"] = [
        {"title": c.title, "price": c.price, "source_note": c.source_note}
        for c in research.comps
    ]

    # --- Phase 2: strategy ---
    strategy_brief = (
        f"Listing: {tc['listing_text']}\n"
        f"Asking price: {research.asking_price}\n"
        f"Fair price range: {research.fair_price_low}-{research.fair_price_high}\n"
        f"Buyer max budget: {tc['budget']}\n"
        f"Urgency: {tc['urgency']}\n"
        f"Dealbreakers: {tc['dealbreakers'] or 'none'}"
    )
    try:
        strategy = run_strategy(strategy_brief)
    except Exception as e:
        result["error_stage"] = "strategy"
        result["error_message"] = str(e)
        result["duration_sec"] = round(time.time() - t_start, 1)
        return result

    result["opening_offer"] = strategy.opening_offer
    result["walkaway_price"] = strategy.walkaway_price
    result["concession_ladder"] = strategy.concession_ladder
    result["strategy_rationale"] = strategy.rationale

    # --- Phase 3: negotiation (up to 2 scripted rounds) ---
    transcript = [
        {
            "role": "agent_message",
            "text": f"Round 1 opening — offer {money(strategy.opening_offer)}.",
        }
    ]
    round_number = 1
    outcome_move = None
    seller_replies = [tc.get("seller_reply")]
    if tc.get("seller_reply_2"):
        seller_replies.append(tc["seller_reply_2"])

    for seller_reply in seller_replies:
        if seller_reply is None:
            break
        transcript.append({"role": "seller_reply", "text": seller_reply})
        neg_brief = (
            f"Opening offer: {strategy.opening_offer}\n"
            f"Concession ladder: {strategy.concession_ladder}\n"
            f"Walk-away price: {strategy.walkaway_price}\n"
            f"Round: {round_number}\n"
            f"Seller's latest real reply: {seller_reply}\n"
            f"Prior transcript:\n"
            + "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
        )
        try:
            move = run_negotiation_move(neg_brief)
        except Exception as e:
            result["error_stage"] = f"negotiation_round_{round_number}"
            result["error_message"] = str(e)
            result["duration_sec"] = round(time.time() - t_start, 1)
            result["transcript"] = transcript
            return result

        transcript.append(
            {
                "role": "agent_message",
                "text": f"Round {round_number} decision — {move.action}: {move.message_to_seller} "
                f"(reasoning: {move.reasoning}; breaks_walkaway={move.breaks_walkaway})",
            }
        )
        outcome_move = move
        if move.action in ("accept", "walk_away"):
            break
        round_number += 1

    result["rounds_run"] = round_number
    result["last_action"] = outcome_move.action if outcome_move else None
    result["breaks_walkaway_flagged"] = (
        outcome_move.breaks_walkaway if outcome_move else None
    )
    result["reasoning_present"] = (
        1 if (outcome_move and outcome_move.reasoning and outcome_move.reasoning.strip()) else 0
    )
    result["transcript"] = transcript

    # --- Phase 4: final outcome (only if negotiation actually terminated) ---
    if outcome_move and outcome_move.action in ("accept", "walk_away"):
        summary = (
            f"Action taken: {outcome_move.action}\n"
            f"Reasoning: {outcome_move.reasoning}\n"
            f"Asking price: {research.asking_price}\n"
            f"Opening offer: {strategy.opening_offer}\n"
            f"Walk-away price: {strategy.walkaway_price}\n"
            f"Rounds played: {round_number}\n"
            f"Full transcript:\n" + "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
        )
        try:
            final = run_final_outcome(summary)
            result["outcome"] = final.outcome
            result["final_price"] = final.final_price
            result["savings_vs_ask"] = final.savings_vs_ask
            result["stop_reason"] = final.reason
            result["next_action"] = final.next_action
        except Exception as e:
            result["error_stage"] = "final_outcome"
            result["error_message"] = str(e)
    else:
        result["outcome"] = "not_terminated_within_eval_budget"

    result["duration_sec"] = round(time.time() - t_start, 1)
    return result


def price_movement_pct(r: dict):
    """% moved from asking price toward (or past) the buyer's favor. None if not a closed deal."""
    if r.get("outcome") != "deal_closed":
        return None
    asking = r.get("asking_price")
    final = r.get("final_price")
    if not asking:
        return None
    return round((asking - final) / asking * 100, 1)


def main():
    print(f"Running {len(TEST_CASES)} eval test cases against {GROQ_MODEL_ID}...\n")
    results = []

    if MLFLOW_AVAILABLE:
        db_path = ROOT / "evals" / "mlflow.db"
        mlflow.set_tracking_uri(f"sqlite:///{db_path}")
        mlflow.set_experiment("olx-negotiation-agent-evals")

    for tc in TEST_CASES:
        print(f"  {tc['id']} — {tc['label']} ...", end=" ", flush=True)
        try:
            r = run_one(tc)
        except Exception as e:
            r = {
                "id": tc["id"],
                "label": tc["label"],
                "error_stage": "harness",
                "error_message": f"{e}\n{traceback.format_exc()}",
            }
        results.append(r)
        pct = price_movement_pct(r)
        r["price_movement_pct"] = pct
        status = r.get("outcome") or f"FAILED at {r.get('error_stage')}"
        print(f"done ({status}, {r.get('duration_sec', '?')}s)")

        if MLFLOW_AVAILABLE:
            with mlflow.start_run(run_name=f"{tc['id']}_{GROQ_MODEL_ID}"):
                mlflow.set_tags(
                    {
                        "test_case": tc["id"],
                        "label": tc["label"],
                        "model": GROQ_MODEL_ID,
                    }
                )
                mlflow.log_param("budget", tc["budget"])
                mlflow.log_param("urgency", tc["urgency"])
                if r.get("comps_count") is not None:
                    mlflow.log_metric("comps_count", r["comps_count"])
                if r.get("rounds_run") is not None:
                    mlflow.log_metric("rounds_run", r["rounds_run"])
                if r.get("reasoning_present") is not None:
                    mlflow.log_metric("reasoning_present", r["reasoning_present"])
                if pct is not None:
                    mlflow.log_metric("price_movement_pct", pct)
                mlflow.log_metric("outcome_deal_closed", 1 if r.get("outcome") == "deal_closed" else 0)
                mlflow.log_metric("errored", 1 if r.get("error_stage") else 0)
                mlflow.log_metric("duration_sec", r.get("duration_sec", 0))

    out_path = ROOT / "evals" / "eval_results.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nWrote {out_path}")
    if MLFLOW_AVAILABLE:
        db_path = ROOT / "evals" / "mlflow.db"
        print(f"MLflow runs logged to sqlite:///{db_path}")
        print("View with: mlflow ui --backend-store-uri", f"sqlite:///{db_path}")


if __name__ == "__main__":
    main()
