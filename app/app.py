"""
OLX Negotiation Copilot — Streamlit app.

Implements DESIGN_DOC.md's workflow end to end:
research -> strategy (user confirms) -> negotiation loop (human relays each
message to/from the real OLX chat) -> fixed-schema final outcome message.

Run:
    export GROQ_API_KEY=...   # or paste it in the sidebar
    streamlit run app.py
"""
import os
import re
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(__file__))
from agent import (  # noqa: E402
    run_research,
    run_strategy,
    run_negotiation_move,
    run_final_outcome,
)
from state import NegotiationState  # noqa: E402

st.set_page_config(page_title="OLX Negotiation Copilot", page_icon="🤝", layout="centered")

# --- API key (sidebar, kept out of chat/history) --------------------------
with st.sidebar:
    st.markdown("### Setup")
    key_input = st.text_input(
        "Groq API key",
        value=os.environ.get("GROQ_API_KEY", ""),
        type="password",
        help="Stored only for this session, used to call Groq directly.",
    )
    if key_input:
        os.environ["GROQ_API_KEY"] = key_input
    serper_key_input = st.text_input(
        "Serper API key",
        value=os.environ.get("SERPER_API_KEY", ""),
        type="password",
        help="From serper.dev — used for the live comp-price search.",
    )
    if serper_key_input:
        os.environ["SERPER_API_KEY"] = serper_key_input
    st.caption(
        "This app never logs into your OLX account. You paste the agent's "
        "suggested messages into the real OLX chat yourself, and paste the "
        "seller's real replies back in here."
    )
    if st.button("Start a new negotiation", use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.title("🤝 OLX Negotiation Copilot")
st.caption("One listing. One seller. A researched strategy, and a disciplined walk-away price.")

if "state" not in st.session_state:
    st.session_state.state = NegotiationState()
state: NegotiationState = st.session_state.state

if not os.environ.get("GROQ_API_KEY") or not os.environ.get("SERPER_API_KEY"):
    st.info("Add your Groq and Serper API keys in the sidebar to start.")
    st.stop()


def money(v):
    return f"₹{v:,.0f}" if v is not None else "—"


# ---------------------------------------------------------------------------
# PHASE 1 — RESEARCH
# ---------------------------------------------------------------------------
st.subheader("1. The listing")

if state.phase == "research":
    listing_text = st.text_area(
        "Paste the listing's title, price, and description as text",
        value=state.listing_text,
        height=150,
        placeholder="e.g. iPhone 12, 128GB, blue, minor scratches on back, asking ₹16,000, "
        "posted 12 days ago, Bengaluru...",
    )
    st.caption(
        "⚠️ A bare OLX link alone won't work — OLX blocks automated fetching, so the "
        "agent can't open it for you. Copy the title, price, and condition from the "
        "listing page and paste them here as text."
    )
    is_bare_url = bool(re.fullmatch(r"\s*https?://\S+\s*", listing_text))
    if is_bare_url:
        st.warning(
            "That looks like just a link. Please paste the listing's title, price, "
            "and condition as text instead — OLX doesn't allow this app to open the "
            "link automatically."
        )
    if st.button(
        "Research a fair price", type="primary", disabled=not listing_text.strip() or is_bare_url
    ):
        state.listing_text = listing_text
        with st.spinner("Searching for comparable listings..."):
            try:
                result = run_research(listing_text)
            except Exception as e:
                st.error(f"Research failed: {e}")
                st.stop()
        state.asking_price = result.asking_price
        state.fair_price_low = result.fair_price_low
        state.fair_price_high = result.fair_price_high
        state.research_confidence_note = result.confidence_note
        state.comps_summary = "\n".join(
            f"- {c.title} — {money(c.price)} ({c.source_note})" for c in result.comps
        )
        state.phase = "strategy"
        st.rerun()
else:
    st.text_area("Listing", value=state.listing_text, height=100, disabled=True)

if state.fair_price_low is not None:
    st.success(
        f"Asking price: {money(state.asking_price)}  |  "
        f"Fair-price range: {money(state.fair_price_low)} – {money(state.fair_price_high)}"
    )
    st.caption(state.research_confidence_note)
    with st.expander("Comps found"):
        st.markdown(state.comps_summary or "_none_")

# ---------------------------------------------------------------------------
# PHASE 2 — STRATEGY
# ---------------------------------------------------------------------------
if state.phase in ("strategy", "negotiate", "done") and state.fair_price_low is not None:
    st.subheader("2. Your constraints")

    if state.phase == "strategy":
        col1, col2 = st.columns(2)
        with col1:
            budget = st.number_input(
                "Max budget (₹)", min_value=0.0,
                value=state.budget or float(state.fair_price_high or state.asking_price),
                step=500.0,
            )
        with col2:
            urgency = st.selectbox("Urgency", ["Low", "Medium", "High"], index=1)
        dealbreakers = st.text_input("Dealbreakers / must-haves (optional)", value=state.dealbreakers)

        if st.button("Propose a strategy", type="primary"):
            state.budget, state.urgency, state.dealbreakers = budget, urgency, dealbreakers
            brief = (
                f"Listing: {state.listing_text}\n"
                f"Asking price: {state.asking_price}\n"
                f"Fair price range: {state.fair_price_low}-{state.fair_price_high}\n"
                f"Buyer max budget: {budget}\n"
                f"Urgency: {urgency}\n"
                f"Dealbreakers: {dealbreakers or 'none'}"
            )
            with st.spinner("Working out a strategy..."):
                try:
                    result = run_strategy(brief)
                except Exception as e:
                    st.error(f"Strategy step failed: {e}")
                    st.stop()
            state.opening_offer = result.opening_offer
            state.walkaway_price = result.walkaway_price
            state.ladder_note = ", ".join(money(v) for v in result.concession_ladder)
            state.last_agent_message = result.rationale
            st.rerun()

    if state.opening_offer is not None:
        st.markdown("**Proposed strategy**")
        st.write(
            f"Opening offer: **{money(state.opening_offer)}**  \n"
            f"Concession ladder: {state.ladder_note}  \n"
            f"Walk-away price: **{money(state.walkaway_price)}**"
        )
        st.caption(state.last_agent_message)

        if state.phase == "strategy":
            if st.button("Confirm strategy and start negotiating", type="primary"):
                state.strategy_confirmed = True
                state.round_number = 1
                state.phase = "negotiate"
                state.add_turn(
                    "agent_message",
                    f"Round 1 opening message — offer {money(state.opening_offer)}. "
                    f"Send this to the seller: paste a firm but friendly opener anchored "
                    f"at {money(state.opening_offer)} into the real OLX chat.",
                )
                st.rerun()

# ---------------------------------------------------------------------------
# PHASE 3 — NEGOTIATION LOOP
# ---------------------------------------------------------------------------
if state.phase in ("negotiate", "done"):
    st.subheader("3. Negotiation")
    st.caption(
        "Copy each suggested message into the real OLX chat, then paste the seller's "
        "real reply back below."
    )

    for turn in state.transcript:
        role = {"agent_message": "🤖 Copilot → you", "seller_reply": "🗣️ Seller → you (relayed)"}.get(
            turn.role, turn.role
        )
        st.markdown(f"**{role}:** {turn.text}")

    if state.phase == "negotiate":
        seller_reply = st.text_area(
            f"Seller's real reply (round {state.round_number})",
            key=f"seller_reply_{state.round_number}",
            placeholder="Paste exactly what the seller said back to you...",
        )
        if st.button("Send seller's reply to the agent", disabled=not seller_reply.strip()):
            state.add_turn("seller_reply", seller_reply)
            brief = (
                f"Opening offer: {state.opening_offer}\n"
                f"Concession ladder: {state.ladder_note}\n"
                f"Walk-away price: {state.walkaway_price}\n"
                f"Round: {state.round_number}\n"
                f"Seller's latest real reply: {seller_reply}\n"
                f"Prior transcript:\n"
                + "\n".join(f"{t.role}: {t.text}" for t in state.transcript)
            )
            with st.spinner("Reading the seller's reply..."):
                try:
                    move = run_negotiation_move(brief)
                except Exception as e:
                    st.error(f"Negotiation step failed: {e}")
                    st.stop()

            if move.breaks_walkaway:
                st.warning(
                    f"⚠️ The agent flagged that this move would go below your walk-away "
                    f"price of {money(state.walkaway_price)}. Reasoning: {move.reasoning}"
                )

            if move.action in ("accept", "walk_away"):
                # Move to final outcome.
                summary = (
                    f"Action taken: {move.action}\n"
                    f"Reasoning: {move.reasoning}\n"
                    f"Asking price: {state.asking_price}\n"
                    f"Opening offer: {state.opening_offer}\n"
                    f"Walk-away price: {state.walkaway_price}\n"
                    f"Rounds played: {state.round_number}\n"
                    f"Full transcript:\n"
                    + "\n".join(f"{t.role}: {t.text}" for t in state.transcript)
                    + f"\nseller_reply: {seller_reply}"
                )
                with st.spinner("Wrapping up..."):
                    try:
                        final = run_final_outcome(summary)
                    except Exception as e:
                        st.error(f"Final outcome step failed: {e}")
                        st.stop()
                state.outcome = final.outcome
                state.final_price = final.final_price
                state.savings_vs_ask = final.savings_vs_ask
                state.stop_reason = final.reason
                state.next_action = final.next_action
                state.phase = "done"
                st.rerun()
            else:
                state.add_turn(
                    "agent_message",
                    f"Round {state.round_number + 1} — {move.action}: {move.message_to_seller}\n"
                    f"(Reasoning: {move.reasoning})",
                )
                state.round_number += 1
                st.rerun()

        if st.button("End negotiation now (I'll decide)"):
            state.outcome = "walked_away"
            state.stop_reason = "Ended manually by the user."
            state.next_action = "Review the transcript above and decide your own next step."
            state.phase = "done"
            st.rerun()

# ---------------------------------------------------------------------------
# PHASE 4 — FINAL OUTCOME (fixed schema, design doc 4b critical constraint)
# ---------------------------------------------------------------------------
if state.phase == "done":
    st.subheader("4. Outcome")
    label = "✅ Deal closed" if state.outcome == "deal_closed" else "🚪 Walked away"
    st.markdown(f"### {label}")
    if state.final_price is not None:
        st.write(f"**Final price:** {money(state.final_price)}")
    if state.savings_vs_ask is not None:
        st.write(f"**Savings vs. original ask:** {money(state.savings_vs_ask)}")
    st.write(f"**Why it stopped here:** {state.stop_reason}")
    st.write(f"**Next action:** {state.next_action}")

    st.divider()
    st.caption(
        "Not persisted anywhere by default (design doc §5). Copy the summary below if "
        "you want to keep it."
    )
    st.code(
        f"Outcome: {state.outcome}\n"
        f"Final price: {state.final_price}\n"
        f"Savings vs ask: {state.savings_vs_ask}\n"
        f"Reason: {state.stop_reason}\n"
        f"Next action: {state.next_action}\n"
        f"Rounds: {state.round_number}",
        language="text",
    )
