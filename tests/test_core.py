"""
Unit tests for the parts of this project that don't require a live Groq/Serper
call: the fixed Pydantic output schemas every agent phase must honor, and the
price-movement math the eval harness and dashboard both report.

These are deliberately narrow — they don't (and can't, without paid API calls)
test the agent's actual reasoning. That's what evals/EVAL_SCORECARD.md is for.
This file exists so a CI run can catch schema drift or a math regression
before either of those show up as a silent bad number in the dashboard.
"""
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "evals"))
sys.path.insert(0, str(ROOT / "dashboard"))

from agent import Comp, ResearchResult, StrategyProposal, NegotiationMove, FinalOutcome  # noqa: E402


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

def test_research_result_accepts_valid_payload():
    r = ResearchResult(
        asking_price=12000,
        listing_summary="Used sofa, good condition",
        days_listed_signal="unknown",
        comps=[Comp(title="Similar sofa, OLX Pune", price=11000, source_note="OLX Pune listing")],
        fair_price_low=10500,
        fair_price_high=11800,
        confidence_note="3 comps found, moderate confidence",
    )
    assert r.asking_price == 12000
    assert len(r.comps) == 1


def test_research_result_allows_null_fair_price_when_no_comps():
    r = ResearchResult(
        asking_price=8000,
        listing_summary="Niche item, no comps found",
        days_listed_signal="unknown",
        comps=[],
        confidence_note="No comparable listings found — range is unverified",
    )
    assert r.fair_price_low is None
    assert r.fair_price_high is None


def test_research_result_rejects_missing_required_field():
    with pytest.raises(ValidationError):
        ResearchResult(listing_summary="missing asking_price and comps")


def test_strategy_proposal_shape():
    s = StrategyProposal(
        opening_offer=10000,
        concession_ladder=[10500, 11000, 11500],
        walkaway_price=12000,
        rationale="Anchored below the fair-price range with room to concede.",
    )
    assert s.opening_offer < s.walkaway_price
    assert s.concession_ladder == sorted(s.concession_ladder)


def test_negotiation_move_action_field_present():
    m = NegotiationMove(
        action="counter",
        message_to_seller="Would you consider ₹11,000?",
        reasoning="Seller's first reply left room to move.",
        breaks_walkaway=False,
    )
    assert m.action in ("counter", "hold", "accept", "walk_away")
    assert isinstance(m.breaks_walkaway, bool)


def test_final_outcome_allows_null_price_on_walkaway():
    f = FinalOutcome(
        outcome="walked_away",
        reason="Seller wouldn't move within 5 rounds.",
        next_action="Look for a comparable listing from a different seller.",
    )
    assert f.final_price is None
    assert f.outcome in ("deal_closed", "walked_away")


# ---------------------------------------------------------------------------
# price_movement_pct math — imported from both call sites to guard against
# the two implementations (evals/run_eval.py and dashboard/live_agent.py)
# silently drifting apart.
# ---------------------------------------------------------------------------

def test_price_movement_pct_matches_across_both_implementations():
    from live_agent import price_movement_pct as dash_pct

    # dashboard's signature: (outcome, asking_price, final_price)
    assert dash_pct("deal_closed", 12000, 10800) == 10.0
    assert dash_pct("walked_away", 12000, None) is None
    assert dash_pct("deal_closed", None, 10800) is None


def test_price_movement_pct_zero_movement():
    from live_agent import price_movement_pct as dash_pct

    assert dash_pct("deal_closed", 12000, 12000) == 0.0
