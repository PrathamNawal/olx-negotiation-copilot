"""
Agent construction for the OLX Negotiation Copilot — Agno + Groq.

Maps directly to DESIGN_DOC.md:
- Section 1/2: single ReAct-style agent, tools = web search only.
- Section 4b: system prompt rules (never invent a price, respect walk-away,
  fixed final-outcome schema).
- Section 4d: web search is the only tool. Started as free scraped
  DuckDuckGo search; switched to the Serper API (a paid-but-free-tier key)
  after live testing showed this sandbox's egress to every scraped search
  backend was unreliable — see search_web()'s docstring below.

Each phase gets its own Agent instance sharing the same model/tools/base
rules, but with a phase-specific instruction and a Pydantic output_schema
so the Streamlit app can parse results reliably instead of scraping free text.
"""
import os
import time
from typing import List, Optional

import requests
from pydantic import BaseModel, Field

from agno.agent import Agent
from agno.models.groq import Groq
from agno.tools import tool

SERPER_URL = "https://google.serper.dev/search"

# Design doc 4a recommended Groq's openai/gpt-oss-120b (built for reasoning
# + tool use, Agno's own default for this provider). Switched to the 20b
# sibling live in testing after 120b's free-tier daily token quota (200k
# TPD) was exhausted by testing itself — same family, separate quota
# bucket, verified working end-to-end at this size too. llama-3.3-70b-
# versatile (the other candidate) isn't available on this account's key.
GROQ_MODEL_ID = os.environ.get("GROQ_MODEL_ID", "openai/gpt-oss-20b")
TEMPERATURE = 0.4  # design doc 4a: low enough for numeric state discipline
MAX_TOKENS = 700
TIMEOUT = 30

BASE_RULES = """
You are a negotiation strategist helping a buyer negotiate the price of ONE
specific OLX (India) listing. You never talk to the seller directly — the
user relays your suggested messages into the real OLX chat and reports the
seller's real replies back to you.

Hard rules, never break these:
- Never state a price comparison or "fair price" claim that is not backed by
  a search result you actually retrieved this session. If you cannot find
  good comps, say so explicitly and lower your confidence — do not invent
  numbers.
- Track and respect the agreed walk-away price once one is set. Never
  recommend accepting below it without explicitly flagging that you are
  breaking the rule and asking the user to confirm first.
- Be concise. A buyer is going to copy what you write directly into a real
  chat with a stranger — write like a person, not a template.
"""


@tool(name="search_comparable_listings")
def search_web(query: str, max_results: int = 8) -> str:
    """Search the web for comparable listing prices for an item.

    Args:
        query: a plain-text search query, e.g. "iPhone 12 128GB used price OLX India".
        max_results: how many results to return (default 8).
    """
    # Switched from free scraped DuckDuckGo search to the Serper API
    # (Google Search results, API-key based) after testing showed this
    # sandbox's egress to every scraped search backend was unreliable
    # (empty results, timeouts, hangs — traced to the sandbox's own egress
    # proxy, not the search providers). A real API call is more reliable
    # than scraping through that proxy.
    api_key = os.environ.get("SERPER_API_KEY")
    if not api_key:
        return "Search unavailable: SERPER_API_KEY is not set. Treat this as zero comps found."

    last_err = None
    for attempt in range(2):
        try:
            resp = requests.post(
                SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": max_results, "gl": "in"},  # gl=in: India results
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            organic = data.get("organic", [])
            if not organic:
                return f"No results found for query: {query!r}."
            lines = [
                f"- {r.get('title', '')}: {r.get('snippet', '')} (source: {r.get('link', '')})"
                for r in organic[:max_results]
            ]
            return "\n".join(lines)
        except Exception as e:  # noqa: BLE001 - network layer can still be flaky
            last_err = e
            time.sleep(1.0)
    return (
        f"Search failed after retries for query {query!r}: {last_err}. "
        "Treat this as zero comps found for this query and say so honestly "
        "rather than guessing a price."
    )


def _model(max_tokens: int = MAX_TOKENS) -> Groq:
    return Groq(
        id=GROQ_MODEL_ID,
        temperature=TEMPERATURE,
        max_tokens=max_tokens,
        timeout=TIMEOUT,
        retries=1,
        delay_between_retries=2,
    )


# ---------------------------------------------------------------------------
# Phase 1: Research — parse listing, search for comps, produce a fair-price
# range with a confidence note (design doc workflow steps 2-3).
# ---------------------------------------------------------------------------
class Comp(BaseModel):
    title: str
    price: float
    source_note: str = Field(
        description="a SHORT plain-text note under 10 words, e.g. 'OLX Mumbai "
        "listing, similar condition' — never a URL or any encoded/tracking text"
    )


class ResearchResult(BaseModel):
    asking_price: float
    listing_summary: str = Field(description="1-2 sentence summary of the item/condition")
    days_listed_signal: str = Field(
        description="what the listing's age (if inferable) suggests about seller flexibility, or 'unknown'"
    )
    comps: List[Comp]
    fair_price_low: Optional[float] = Field(
        default=None, description="null if genuinely no comps were found"
    )
    fair_price_high: Optional[float] = Field(
        default=None, description="null if genuinely no comps were found"
    )
    confidence_note: str = Field(
        description="how many comps were found and how confident this range is, stated honestly"
    )


def _make_research_tool_agent() -> Agent:
    """Stage 1: real web search + reasoning. No output_schema here — Groq
    rejects combining JSON response_format with tool calling in one call, so
    structured output has to be a separate stage (stage 2 below)."""
    return Agent(
        model=_model(max_tokens=1400),  # needs room for tool reasoning + a full comps list
        tools=[search_web],
        tool_call_limit=4,
        description="Researches a fair price for one specific OLX listing using live web search.",
        instructions=[
            BASE_RULES,
            "Given a pasted OLX listing, first extract the asking price and key details.",
            "The ONLY tool you have is search_comparable_listings. You cannot open URLs, "
            "fetch pages, or browse — do not attempt to call any other tool (e.g. "
            "opening a file or a link). Work only from the title/snippet text the "
            "search tool returns.",
            "Use the search tool to find 5-10 comparable listings/prices for this "
            "category of item in India (OLX or similar marketplaces). Always call the "
            "tool with a plain-text query string, e.g. 'iPhone 12 128GB price OLX "
            "India'. Try 2-3 different phrasings if results are weak or generic "
            "(e.g. add the city, or 'used' / 'second hand'). Search snippets often "
            "contain several prices in one result (e.g. a category page listing many "
            "items) — pull out each distinct price you can see as its own comp. "
            "General web search sometimes returns generic retail pages instead of real "
            "second-hand asking prices — if that happens, say so in your confidence "
            "note rather than treating a retail/new price as a comp for a used item.",
            "Structure your answer in this exact order, comps list FIRST so it never "
            "gets cut off if you run long:",
            "1) A section titled 'COMPS FOUND:' — a bullet list, one bullet per "
            "distinct price you saw in the search results, in the form "
            "'- <item/title> — ₹<price> (<short source like \"OLX Pune\">)'. Never "
            "paste a full URL or any long encoded text — a short place/site name is "
            "enough. List up to 10 of the most relevant distinct prices you actually "
            "saw — do not invent more, but do not list every duplicate either if there "
            "are many. Only write 'COMPS FOUND: none' if the search truly returned no "
            "prices at all.",
            "2) After that, a short summary: the asking price, item summary, any "
            "signal from how long it's been listed, and a fair-price range with an "
            "honest confidence note (say plainly if comps were thin). Keep this part "
            "brief — the comps list above is the important part.",
        ],
        markdown=False,
    )


def _make_research_parser_agent() -> Agent:
    """Stage 2: structures stage 1's real findings into ResearchResult. No
    tools here, so output_schema works cleanly."""
    return Agent(
        model=_model(max_tokens=1600),  # up to 10 comps as structured JSON is verbose
        description="Structures research notes into the fixed ResearchResult schema.",
        instructions=[
            "You will be given research notes about an OLX listing that already include "
            "real search findings, ending in a 'COMPS FOUND:' bullet list. Extract every "
            "bullet from that section into the comps field — do not skip any, and do not "
            "add, invent, or adjust any price that isn't already present in the notes. "
            "If 'COMPS FOUND: none' is stated, comps must be an empty list.",
            "For each comp's source_note, write a short plain-text summary (e.g. 'OLX "
            "Bengaluru listing') — never copy a URL or any long encoded/tracking text "
            "into source_note, even if one appears in the notes. Keep every field "
            "concise; you do not need to reproduce full URLs anywhere in your output.",
        ],
        output_schema=ResearchResult,
        markdown=False,
    )


class ResearchError(RuntimeError):
    pass


class AgentOutputError(RuntimeError):
    """Raised when a phase's structured output couldn't be obtained even
    after a retry. Observed live in testing: Groq/the model occasionally
    returns malformed JSON (schema validation or generation errors) instead
    of a valid structured object, across every phase — not just research.
    Every phase call in this app should go through _run_structured so a
    transient bad response doesn't crash the app with a raw AttributeError."""


def _run_structured(make_agent, input_text: str, attempts: int = 3):
    last_content = None
    for i in range(attempts):
        prompt = input_text
        if i > 0:
            prompt += (
                "\n\n(Your previous response was not valid structured output — "
                "return ONLY the requested fields in the required schema, nothing else.)"
            )
        result = make_agent().run(input=prompt).content
        if not isinstance(result, str):
            return result
        last_content = result
    raise AgentOutputError(
        f"Model did not return valid structured output after {attempts} attempts: {last_content!r}"
    )


def run_research(listing_text: str) -> ResearchResult:
    """Two-stage research: real tool-augmented reasoning, then structuring.
    Kept as one function so callers don't need to know about the Groq
    tools/json-mode limitation that forced the split.

    Observed live in testing: the model sometimes skips calling the search
    tool entirely and just answers from the listing text alone (forcing
    tool_choice="required" on Groq does NOT fix this — it instead makes the
    model's own final-answer turn error out, since Groq then requires a tool
    call on every turn including the synthesis step). So instead: check
    whether the tool was actually called via the run's recorded tool
    executions, and retry once with an explicit nudge if not.
    """
    prompt = listing_text
    notes = ""
    for attempt in range(2):
        run_out = _make_research_tool_agent().run(input=prompt)
        notes = run_out.content or ""
        called = any(
            t.tool_name == "search_comparable_listings" and not t.tool_call_error
            for t in (run_out.tools or [])
        )
        if called:
            break
        prompt = (
            f"{listing_text}\n\n"
            "(You did not call search_comparable_listings last time — you must "
            "call it at least once with a plain-text query before writing your "
            "summary. Do not answer from the listing text alone.)"
        )
    else:
        return ResearchResult(
            asking_price=0.0,
            listing_summary=listing_text[:200],
            days_listed_signal="unknown",
            comps=[],
            fair_price_low=0.0,
            fair_price_high=0.0,
            confidence_note=(
                "Search was not performed after two attempts — treat this "
                "range as unverified, not a real fair-price estimate."
            ),
        )

    parsed = _run_structured(
        _make_research_parser_agent, f"Listing: {listing_text}\n\nResearch notes:\n{notes}"
    )
    # Safety net, not a grounding claim: if genuinely no comps were found,
    # anchor the range to the asking price so downstream phases (which
    # assume a numeric range) don't crash — the honesty lives in
    # confidence_note and comps=[], which the UI surfaces directly.
    if parsed.fair_price_low is None:
        parsed.fair_price_low = parsed.asking_price
    if parsed.fair_price_high is None:
        parsed.fair_price_high = parsed.asking_price
    return parsed


# ---------------------------------------------------------------------------
# Phase 2: Strategy — propose opening offer, concession ladder, walk-away
# price (workflow step 5). User must confirm before any message is sent.
# ---------------------------------------------------------------------------
class StrategyProposal(BaseModel):
    opening_offer: float
    concession_ladder: List[float] = Field(
        description="e.g. [12000, 12800, 13500] — successive fallback offers if seller pushes back"
    )
    walkaway_price: float
    rationale: str = Field(description="why this opening/ladder/walk-away, tied to the research")


def _make_strategy_agent() -> Agent:
    return Agent(
        model=_model(max_tokens=900),
        description="Proposes a negotiation strategy (opening offer, concession ladder, walk-away price).",
        instructions=[
            BASE_RULES,
            "Given the fair-price research, the buyer's max budget, urgency, and any "
            "dealbreakers, propose a negotiation strategy.",
            "The walk-away price must never exceed the buyer's stated max budget.",
            "The opening offer should be anchored below the fair-price range, leaving "
            "room to concede across 2-4 rounds without exceeding the walk-away price.",
        ],
        output_schema=StrategyProposal,
        markdown=False,
    )


def run_strategy(brief_text: str) -> StrategyProposal:
    return _run_structured(_make_strategy_agent, brief_text)


# ---------------------------------------------------------------------------
# Phase 3: Negotiation loop — react to the seller's real reply each round
# (workflow step 7). This is the core ReAct/agentic decision point.
# ---------------------------------------------------------------------------
class NegotiationMove(BaseModel):
    action: str = Field(description="one of: counter, hold, accept, walk_away")
    message_to_seller: str = Field(
        description="the exact message for the user to paste into the real OLX chat; "
        "empty string if action is accept or walk_away and nothing further needs sending"
    )
    reasoning: str = Field(description="your read of the seller's flexibility from their last reply")
    breaks_walkaway: bool = Field(
        description="true only if this action would mean accepting above the walk-away price"
    )


def _make_negotiation_agent() -> Agent:
    return Agent(
        model=_model(max_tokens=900),
        description="Reacts to the seller's real reply and decides the next negotiation move.",
        instructions=[
            BASE_RULES,
            "You will be given the negotiation strategy (opening offer, concession ladder, "
            "walk-away price), the round number, and the seller's latest real reply.",
            "Decide exactly one action: counter (send the next ladder offer or a variant), "
            "hold (repeat/reinforce current offer without conceding), accept (seller met "
            "or beat the walk-away price), or walk_away (seller won't move and the ladder "
            "is exhausted).",
            "If accepting would require going below the walk-away price, set "
            "breaks_walkaway=true and explain why you're flagging it instead of silently "
            "recommending it.",
        ],
        output_schema=NegotiationMove,
        markdown=False,
    )


def run_negotiation_move(brief_text: str) -> NegotiationMove:
    return _run_structured(_make_negotiation_agent, brief_text)


# ---------------------------------------------------------------------------
# Phase 4: Final outcome — fixed schema (design doc 4b critical constraint).
# ---------------------------------------------------------------------------
class FinalOutcome(BaseModel):
    outcome: str = Field(description="one of: deal_closed, walked_away")
    final_price: Optional[float] = None
    savings_vs_ask: Optional[float] = None
    reason: str = Field(description="why the negotiation stopped here")
    next_action: str = Field(description="what the user should do next")


def _make_final_agent() -> Agent:
    return Agent(
        model=_model(max_tokens=1000),
        description="Writes the final, fixed-schema outcome message for a closed or abandoned negotiation.",
        instructions=[
            BASE_RULES,
            "Summarize the negotiation outcome using the fixed schema fields. Be specific "
            "about why it stopped here (which offer/round triggered the stop).",
        ],
        output_schema=FinalOutcome,
        markdown=False,
    )


def run_final_outcome(summary_text: str) -> FinalOutcome:
    return _run_structured(_make_final_agent, summary_text)
