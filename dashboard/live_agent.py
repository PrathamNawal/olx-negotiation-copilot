"""
Runs the REAL agent — real Groq calls, real Serper search — using whatever
config version is passed in, instead of always using app/agent.py's
hardcoded defaults. This is what makes the Play/Tweak page's edits actually
change behavior instead of just being a cosmetic form.

Reuses agent.py's actual Pydantic schemas, the real search_web tool, and its
_run_structured retry helper directly — this file's job is to swap in
version-specific prompts/model/temperature around that same real logic, not
reimplement the agent.
"""
import sys
import time
from pathlib import Path
from typing import Callable, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from agno.agent import Agent  # noqa: E402
from agno.models.groq import Groq  # noqa: E402

import agent as base_agent  # noqa: E402
from agent import (  # noqa: E402
    ResearchResult,
    StrategyProposal,
    NegotiationMove,
    FinalOutcome,
    search_web,
    _run_structured,
)

TraceFn = Optional[Callable[[str], None]]


def _model(version: dict, max_tokens: int) -> Groq:
    return Groq(
        id=version["model_id"],
        temperature=version["temperature"],
        max_tokens=max_tokens,
        timeout=30,
        retries=1,
        delay_between_retries=2,
    )


def _split(instructions_text: str) -> List[str]:
    """Version prompts are stored as one editable text blob (what the Play
    page's textarea edits); Agno wants a list of instruction strings, so
    split back on the blank-line join used when the blob was built."""
    return [instructions_text]


def build_research_tool_agent(version: dict) -> Agent:
    return Agent(
        model=_model(version, max_tokens=1400),
        tools=[search_web],
        tool_call_limit=4,
        description="Researches a fair price for one specific OLX listing using live web search.",
        instructions=_split(version["prompts"]["research_tool_instructions"]),
        markdown=False,
    )


def build_research_parser_agent(version: dict) -> Agent:
    return Agent(
        model=_model(version, max_tokens=1600),
        description="Structures research notes into the fixed ResearchResult schema.",
        instructions=_split(version["prompts"]["research_parser_instructions"]),
        output_schema=ResearchResult,
        markdown=False,
    )


def build_strategy_agent(version: dict) -> Agent:
    return Agent(
        model=_model(version, max_tokens=900),
        description="Proposes a negotiation strategy (opening offer, concession ladder, walk-away price).",
        instructions=_split(version["prompts"]["strategy_instructions"]),
        output_schema=StrategyProposal,
        markdown=False,
    )


def build_negotiation_agent(version: dict) -> Agent:
    return Agent(
        model=_model(version, max_tokens=900),
        description="Reacts to the seller's real reply and decides the next negotiation move.",
        instructions=_split(version["prompts"]["negotiation_instructions"]),
        output_schema=NegotiationMove,
        markdown=False,
    )


def build_final_agent(version: dict) -> Agent:
    return Agent(
        model=_model(version, max_tokens=1000),
        description="Writes the final, fixed-schema outcome message for a closed or abandoned negotiation.",
        instructions=_split(version["prompts"]["final_instructions"]),
        output_schema=FinalOutcome,
        markdown=False,
    )


def run_research_live(listing_text: str, version: dict, trace: TraceFn = None) -> ResearchResult:
    if trace:
        trace(f"Calling {version['model_id']} with the live search tool...")
    prompt = listing_text
    notes = ""
    for attempt in range(2):
        run_out = build_research_tool_agent(version).run(input=prompt)
        notes = run_out.content or ""
        calls = [t for t in (run_out.tools or []) if t.tool_name == "search_comparable_listings"]
        called = any(not t.tool_call_error for t in calls)
        if trace:
            for t in calls:
                q = (t.tool_args or {}).get("query", "")
                trace(f"  tool call: search_comparable_listings(query={q!r})")
        if called:
            break
        prompt = (
            f"{listing_text}\n\n"
            "(You did not call search_comparable_listings last time — you must "
            "call it at least once with a plain-text query before writing your "
            "summary. Do not answer from the listing text alone.)"
        )
    else:
        if trace:
            trace("Search was never called after 2 attempts — returning an honest zero-comp result.")
        return ResearchResult(
            asking_price=0.0,
            listing_summary=listing_text[:200],
            days_listed_signal="unknown",
            comps=[],
            fair_price_low=0.0,
            fair_price_high=0.0,
            confidence_note="Search was not performed after two attempts — treat this range as unverified.",
        )

    if trace:
        trace("Structuring research notes into the fixed ResearchResult schema...")
    parsed = _run_structured(
        lambda: build_research_parser_agent(version),
        f"Listing: {listing_text}\n\nResearch notes:\n{notes}",
    )
    if parsed.fair_price_low is None:
        parsed.fair_price_low = parsed.asking_price
    if parsed.fair_price_high is None:
        parsed.fair_price_high = parsed.asking_price
    if trace:
        trace(f"Found {len(parsed.comps)} comps. Fair range: {parsed.fair_price_low}-{parsed.fair_price_high}.")
    return parsed


def run_strategy_live(brief_text: str, version: dict, trace: TraceFn = None) -> StrategyProposal:
    if trace:
        trace("Proposing opening offer / concession ladder / walk-away price...")
    return _run_structured(lambda: build_strategy_agent(version), brief_text)


def run_negotiation_move_live(brief_text: str, version: dict, trace: TraceFn = None) -> NegotiationMove:
    if trace:
        trace("Reading the seller's reply and deciding the next move...")
    return _run_structured(lambda: build_negotiation_agent(version), brief_text)


def run_final_outcome_live(summary_text: str, version: dict, trace: TraceFn = None) -> FinalOutcome:
    if trace:
        trace("Writing the fixed-schema final outcome...")
    return _run_structured(lambda: build_final_agent(version), summary_text)


def price_movement_pct(outcome: str, asking_price: Optional[float], final_price: Optional[float]):
    if outcome != "deal_closed" or not asking_price or final_price is None:
        return None
    return round((asking_price - final_price) / asking_price * 100, 1)


def run_quick_eval(version: dict, test_cases: list, trace: TraceFn = None) -> list:
    """Runs the given test cases (from evals/test_cases.py) fully through the
    live pipeline for THIS version and returns per-case result dicts, ready
    to be logged to MLflow by the caller. Real calls only — same code path
    as evals/run_eval.py, just parameterized on a version instead of the
    hardcoded module defaults."""
    results = []
    for tc in test_cases:
        t0 = time.time()
        if trace:
            trace(f"--- {tc['id']}: {tc['label']} ---")
        r = {"id": tc["id"], "label": tc["label"]}
        try:
            research = run_research_live(tc["listing_text"], version, trace)
        except Exception as e:
            r.update({"error_stage": "research", "error_message": str(e)})
            results.append(r)
            continue

        r["comps_count"] = len(research.comps)
        r["asking_price"] = research.asking_price

        strategy_brief = (
            f"Listing: {tc['listing_text']}\n"
            f"Asking price: {research.asking_price}\n"
            f"Fair price range: {research.fair_price_low}-{research.fair_price_high}\n"
            f"Buyer max budget: {tc['budget']}\n"
            f"Urgency: {tc['urgency']}\n"
            f"Dealbreakers: {tc['dealbreakers'] or 'none'}"
        )
        try:
            strategy = run_strategy_live(strategy_brief, version, trace)
        except Exception as e:
            r.update({"error_stage": "strategy", "error_message": str(e)})
            results.append(r)
            continue

        transcript = [{"role": "agent_message", "text": f"Round 1 opening — offer {strategy.opening_offer}."}]
        seller_replies = [tc.get("seller_reply")]
        if tc.get("seller_reply_2"):
            seller_replies.append(tc["seller_reply_2"])
        round_number = 1
        move = None
        for seller_reply in seller_replies:
            if not seller_reply:
                break
            transcript.append({"role": "seller_reply", "text": seller_reply})
            neg_brief = (
                f"Opening offer: {strategy.opening_offer}\n"
                f"Concession ladder: {strategy.concession_ladder}\n"
                f"Walk-away price: {strategy.walkaway_price}\n"
                f"Round: {round_number}\n"
                f"Seller's latest real reply: {seller_reply}\n"
                f"Prior transcript:\n" + "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
            )
            try:
                move = run_negotiation_move_live(neg_brief, version, trace)
            except Exception as e:
                r.update({"error_stage": f"negotiation_round_{round_number}", "error_message": str(e)})
                break
            transcript.append({"role": "agent_message", "text": f"{move.action}: {move.message_to_seller}"})
            if move.action in ("accept", "walk_away"):
                break
            round_number += 1

        r["rounds_run"] = round_number
        r["reasoning_present"] = 1 if (move and move.reasoning and move.reasoning.strip()) else 0

        if move and move.action in ("accept", "walk_away"):
            summary = (
                f"Action taken: {move.action}\nReasoning: {move.reasoning}\n"
                f"Asking price: {research.asking_price}\nOpening offer: {strategy.opening_offer}\n"
                f"Walk-away price: {strategy.walkaway_price}\nRounds played: {round_number}\n"
                "Full transcript:\n" + "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
            )
            try:
                final = run_final_outcome_live(summary, version, trace)
                r["outcome"] = final.outcome
                r["final_price"] = final.final_price
                r["savings_vs_ask"] = final.savings_vs_ask
            except Exception as e:
                r.update({"error_stage": "final_outcome", "error_message": str(e)})
        else:
            r["outcome"] = "not_terminated_within_eval_budget"

        r["price_movement_pct"] = price_movement_pct(
            r.get("outcome"), r.get("asking_price"), r.get("final_price")
        )
        r["duration_sec"] = round(time.time() - t0, 1)
        results.append(r)
    return results
