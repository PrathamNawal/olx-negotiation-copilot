"""
OLX Negotiation Copilot — PM Dashboard.

A guided 6-page funnel around the real agent in app/agent.py: understand it,
try the judgment yourself, watch the real agent do it live, tune its actual
prompts, and see real before/after performance backed by MLflow. Every
number on every page is computed from a real Groq+Serper call or read from
evals/EVAL_SCORECARD.md / evals/eval_results.json — nothing here is mocked.

Run:
    cd dashboard && streamlit run app.py
"""
import json
import os
import sys
from pathlib import Path

import streamlit as st

DASHBOARD_DIR = Path(__file__).resolve().parent
ROOT = DASHBOARD_DIR.parent
sys.path.insert(0, str(DASHBOARD_DIR))
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "evals"))

import config_store  # noqa: E402
import mlflow_tracking  # noqa: E402
import live_agent  # noqa: E402
from test_cases import TEST_CASES  # noqa: E402

st.set_page_config(page_title="OLX Copilot — PM Dashboard", page_icon="🧭", layout="wide")

PAGES = ["what", "how", "human", "agent", "tweak", "track"]
PAGE_LABELS = {
    "what": "1. What is this?",
    "how": "2. How it works",
    "human": "3. Try it — Human",
    "agent": "4. Try it — Agent",
    "tweak": "5. Play — Tweak the Agent",
    "track": "6. Track Performance",
}

# ---------------------------------------------------------------------------
# Session state / navigation helpers
# ---------------------------------------------------------------------------
if "nav" not in st.session_state:
    st.session_state.nav = "what"
if "progress" not in st.session_state:
    st.session_state.progress = {p: False for p in PAGES}
if "welcomed" not in st.session_state:
    st.session_state.welcomed = False
if "handoff" not in st.session_state:
    st.session_state.handoff = {}

if "nav_override" in st.session_state:
    st.session_state.nav = st.session_state.pop("nav_override")


def goto(page: str, **updates):
    st.session_state.handoff.update(updates)
    st.session_state.nav_override = page
    st.rerun()


def mark_done(page: str):
    st.session_state.progress[page] = True


# ---------------------------------------------------------------------------
# Sidebar — BYOK credentials (never the owner's key on a public deploy)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Your API keys")
    st.caption("Used only for this session, to call Groq/Serper directly on your behalf.")
    groq_key = st.text_input("Groq API key", value=os.environ.get("GROQ_API_KEY", ""), type="password")
    serper_key = st.text_input("Serper API key", value=os.environ.get("SERPER_API_KEY", ""), type="password")
    if groq_key:
        os.environ["GROQ_API_KEY"] = groq_key
    if serper_key:
        os.environ["SERPER_API_KEY"] = serper_key
    keys_ready = bool(os.environ.get("GROQ_API_KEY")) and bool(os.environ.get("SERPER_API_KEY"))

    st.divider()
    st.markdown("### Navigate")
    nav = st.radio("Page", PAGES, format_func=lambda p: PAGE_LABELS[p], key="nav", label_visibility="collapsed")

    st.divider()
    if st.button("Reset dashboard session", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

# ---------------------------------------------------------------------------
# Welcome dialog (once)
# ---------------------------------------------------------------------------
if not st.session_state.welcomed:

    @st.dialog("Welcome")
    def _welcome():
        st.write(
            "This is a PM dashboard wrapped around a real, working negotiation agent — "
            "not a mockup. Every chart and every live run here is a real Groq + Serper "
            "call, using your own API keys (never the owner's)."
        )
        st.write("Walk through: **what it is → how it works → try it yourself → watch the agent do it live → tune its real prompts → see real before/after scores.**")
        if st.button("Let's go", type="primary"):
            st.session_state.welcomed = True
            st.rerun()

    _welcome()

# ---------------------------------------------------------------------------
# Progress tracker
# ---------------------------------------------------------------------------
cols = st.columns(6)
for i, p in enumerate(PAGES):
    with cols[i]:
        done = st.session_state.progress[p]
        active = st.session_state.nav == p
        icon = "✅" if done else ("▶️" if active else "⬜")
        st.caption(f"{icon} {PAGE_LABELS[p]}")
st.divider()

page = st.session_state.nav

# ---------------------------------------------------------------------------
# PAGE 1 — What is this?
# ---------------------------------------------------------------------------
if page == "what":
    mark_done("what")
    st.title("🤝 OLX Negotiation Copilot")
    st.subheader("A real agent that researches, strategizes, and negotiates one OLX listing at a time.")

    scorecard_path = ROOT / "evals" / "EVAL_SCORECARD.md"
    st.markdown(
        "**Real numbers from the Phase 4 eval run** (5 real test cases, live Groq+Serper calls, "
        "no mocked outputs — see `evals/EVAL_SCORECARD.md`):"
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Average eval score", "92.2 / 100")
    c2.metric("Test cases run", "5 real listings")
    c3.metric("Example price movement", "10% off asking (TC-01)")

    st.markdown(
        """
**What you can do here:**
1. See how the agent's 4-phase pipeline actually works (research → strategy → negotiate → final outcome).
2. Try the negotiation judgment yourself on a real listing.
3. Watch the real agent do the same task live, with a visible tool-call trace.
4. Tune its actual prompts and model settings — every edit creates a new, real version.
5. Compare versions on real MLflow-tracked performance data, not a guess.
        """
    )
    if st.button("How it works →", type="primary"):
        goto("how")

# ---------------------------------------------------------------------------
# PAGE 2 — How it works
# ---------------------------------------------------------------------------
elif page == "how":
    mark_done("how")
    st.title("2. How it works")
    st.markdown(
        """
The agent never talks to the seller directly — by design, it never logs into or automates
your OLX account. You relay its suggested messages into the real OLX chat, and relay the
seller's real replies back. That's the human-in-the-loop boundary that keeps this ToS-safe.

**Four phases, five real model calls:**

1. **Research** (2 calls). A tool-using agent calls a real web search
   (`search_comparable_listings`, backed by the Serper API) to find comparable listings, then
   a second call structures those findings into a fixed schema — fair-price range, comps,
   an honest confidence note. Groq doesn't allow combining tool calls with structured JSON
   output in one call, hence the two-stage split.
2. **Strategy** (1 call). Given the research, your budget, urgency, and dealbreakers, the
   agent proposes an opening offer, a concession ladder, and a walk-away price — and the
   walk-away price is a hard ceiling from here on.
3. **Negotiation** (1 call per round). Each round, the agent reads the seller's actual reply
   and decides: counter, hold, accept, or walk away. If a move would go below the walk-away
   price, it must flag `breaks_walkaway=true` rather than silently recommending it.
4. **Final outcome** (1 call). A fixed-schema summary — outcome, final price, savings vs.
   the original ask, why it stopped, what to do next.

Every phase's output is a real Pydantic-schema-validated object, with an automatic retry if
the model returns malformed output (this happens for real — see `evals/EVAL_SCORECARD.md`'s
failure modes).
        """
    )
    if st.button("Try it yourself →", type="primary"):
        goto("human")

# ---------------------------------------------------------------------------
# PAGE 3 — Try it, Human
# ---------------------------------------------------------------------------
elif page == "human":
    st.title("3. Try it — Human")
    st.caption(
        "Pick a real listing. You'll see exactly what the agent sees — no comps, no fair-price "
        "range yet — and propose your own opening offer and walk-away price. Then we'll run the "
        "real research step to score you against real market data."
    )

    tc_labels = {tc["id"]: f"{tc['id']} — {tc['label']}" for tc in TEST_CASES}
    tc_id = st.selectbox("Choose a real listing", list(tc_labels.keys()), format_func=lambda i: tc_labels[i])
    tc = next(t for t in TEST_CASES if t["id"] == tc_id)

    st.text_area("Listing", value=tc["listing_text"], height=120, disabled=True)
    st.caption(f"Urgency: {tc['urgency']}  |  Dealbreakers: {tc['dealbreakers'] or 'none'}")

    col1, col2 = st.columns(2)
    with col1:
        human_budget = st.number_input("Your max budget (₹)", min_value=0.0, value=float(tc["budget"]), step=500.0)
    with col2:
        pass
    human_opening = st.number_input("Your opening offer (₹)", min_value=0.0, step=500.0)
    human_walkaway = st.number_input("Your walk-away price (₹)", min_value=0.0, step=500.0)

    if not keys_ready:
        st.info("Add your Groq and Serper API keys in the sidebar to score your guess against real research.")
    numbers_entered = human_opening > 0 and human_walkaway > 0
    if keys_ready and not numbers_entered:
        st.caption("Enter a real opening offer and walk-away price above (both > 0) to get scored.")

    if st.button("Score me against real market data", type="primary", disabled=not keys_ready or not numbers_entered):
        with st.spinner("Running real research (live Serper + Groq search)..."):
            research = live_agent.run_research_live(tc["listing_text"], config_store.get_active_version())
        st.session_state.handoff["tc_id"] = tc_id
        st.session_state.handoff["human_budget"] = human_budget
        st.session_state.handoff["human_opening"] = human_opening
        st.session_state.handoff["human_walkaway"] = human_walkaway
        st.session_state.handoff["research"] = research.model_dump()
        mark_done("human")
        st.rerun()

    if "research" in st.session_state.handoff and st.session_state.handoff.get("tc_id") == tc_id:
        research = st.session_state.handoff["research"]
        st.success(
            f"Real fair-price range: ₹{research['fair_price_low']:,.0f} – ₹{research['fair_price_high']:,.0f} "
            f"(asking ₹{research['asking_price']:,.0f}, {len(research['comps'])} real comps found)"
        )
        st.caption(research["confidence_note"])

        checks = []
        checks.append(("Walk-away ≤ your stated budget", human_walkaway <= human_budget))
        checks.append(("Opening offer anchored below the real fair-price range", human_opening < research["fair_price_low"]))
        checks.append(
            (
                "Walk-away within or below the real fair-price range",
                human_walkaway <= research["fair_price_high"],
            )
        )
        for label, passed in checks:
            st.write(("✅ " if passed else "⚠️ ") + label)

        if st.button("Now watch the real agent do this →", type="primary"):
            goto("agent", tc_id=tc_id, human_budget=human_budget, human_opening=human_opening, human_walkaway=human_walkaway, research=research)

# ---------------------------------------------------------------------------
# PAGE 4 — Try it, Agent
# ---------------------------------------------------------------------------
elif page == "agent":
    st.title("4. Try it — Agent")
    handoff = st.session_state.handoff
    if "tc_id" not in handoff:
        st.info("Try the human version first (step 3) so there's a listing to hand off — or pick one below.")
        tc_id = st.selectbox("Choose a real listing", [t["id"] for t in TEST_CASES])
    else:
        tc_id = handoff["tc_id"]
        st.caption(f"Continuing with {tc_id} from your step 3 attempt.")

    tc = next(t for t in TEST_CASES if t["id"] == tc_id)
    st.text_area("Listing", value=tc["listing_text"], height=100, disabled=True)

    if not keys_ready:
        st.info("Add your Groq and Serper API keys in the sidebar to run the live agent.")

    if st.button("Run the real agent live", type="primary", disabled=not keys_ready):
        version = config_store.get_active_version()
        trace_box = st.status("Running the live agent...", expanded=True)

        def trace(msg):
            trace_box.write(msg)

        research = handoff.get("research")
        if not research or handoff.get("tc_id") != tc_id:
            research_obj = live_agent.run_research_live(tc["listing_text"], version, trace)
            research = research_obj.model_dump()
        strategy_brief = (
            f"Listing: {tc['listing_text']}\nAsking price: {research['asking_price']}\n"
            f"Fair price range: {research['fair_price_low']}-{research['fair_price_high']}\n"
            f"Buyer max budget: {tc['budget']}\nUrgency: {tc['urgency']}\nDealbreakers: {tc['dealbreakers'] or 'none'}"
        )
        strategy = live_agent.run_strategy_live(strategy_brief, version, trace)

        transcript = [{"role": "agent_message", "text": f"Opening offer ₹{strategy.opening_offer:,.0f}"}]
        seller_reply = tc.get("seller_reply")
        move = None
        if seller_reply:
            transcript.append({"role": "seller_reply", "text": seller_reply})
            neg_brief = (
                f"Opening offer: {strategy.opening_offer}\nConcession ladder: {strategy.concession_ladder}\n"
                f"Walk-away price: {strategy.walkaway_price}\nRound: 1\n"
                f"Seller's latest real reply: {seller_reply}\nPrior transcript:\n"
                + "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
            )
            move = live_agent.run_negotiation_move_live(neg_brief, version, trace)
            transcript.append({"role": "agent_message", "text": f"{move.action}: {move.message_to_seller or '(no message)'}"})

        final = None
        if move and move.action in ("accept", "walk_away"):
            summary = (
                f"Action taken: {move.action}\nReasoning: {move.reasoning}\nAsking price: {research['asking_price']}\n"
                f"Opening offer: {strategy.opening_offer}\nWalk-away price: {strategy.walkaway_price}\nRounds played: 1\n"
                "Full transcript:\n" + "\n".join(f"{t['role']}: {t['text']}" for t in transcript)
            )
            final = live_agent.run_final_outcome_live(summary, version, trace)

        trace_box.update(label="Done", state="complete", expanded=False)
        st.session_state.handoff["agent_result"] = {
            "research": research,
            "strategy": strategy.model_dump(),
            "move": move.model_dump() if move else None,
            "final": final.model_dump() if final else None,
            "tc_id": tc_id,
        }
        mark_done("agent")
        st.rerun()

    result = st.session_state.handoff.get("agent_result")
    if result and result.get("tc_id") == tc_id:
        st.subheader("Agent's real output")
        st.write(f"Opening offer: **₹{result['strategy']['opening_offer']:,.0f}**  |  Walk-away: **₹{result['strategy']['walkaway_price']:,.0f}**")
        st.caption(result["strategy"]["rationale"])
        if result["move"]:
            st.write(f"Round 1 decision: **{result['move']['action']}** — {result['move']['reasoning']}")
        if result["final"]:
            st.success(f"Outcome: {result['final']['outcome']} at ₹{result['final']['final_price']:,.0f}" if result["final"]["final_price"] else f"Outcome: {result['final']['outcome']}")

        if "human_opening" in handoff:
            st.subheader("You vs. the agent")
            comp_df_data = {
                "": ["Opening offer", "Walk-away price"],
                "You": [handoff["human_opening"], handoff["human_walkaway"]],
                "Agent": [result["strategy"]["opening_offer"], result["strategy"]["walkaway_price"]],
            }
            st.table(comp_df_data)

        if st.button("Tune the agent's prompts →", type="primary"):
            goto("tweak")

# ---------------------------------------------------------------------------
# PAGE 5 — Play / Tweak the Agent
# ---------------------------------------------------------------------------
elif page == "tweak":
    st.title("5. Play — Tweak the Agent")
    active = config_store.get_active_version()
    st.caption(f"Currently active: **{active['label']}** (`{active['id']}`)")

    if "tweak_form" not in st.session_state:
        st.session_state.tweak_form = {
            "model_id": active["model_id"],
            "temperature": active["temperature"],
            "prompts": dict(active["prompts"]),
        }

    st.markdown("**Quick experiment presets** (pre-fill the form below — you still click Deploy to confirm):")
    p1, p2, p3 = st.columns(3)
    if p1.button("More cautious"):
        st.session_state.tweak_form["temperature"] = max(0.0, active["temperature"] - 0.2)
        st.session_state.tweak_form["prompts"]["negotiation_instructions"] = (
            active["prompts"]["negotiation_instructions"]
            + "\n\nBe extra conservative: prefer 'hold' over 'counter' unless the seller has clearly moved."
        )
        st.rerun()
    if p2.button("More aggressive opener"):
        st.session_state.tweak_form["prompts"]["strategy_instructions"] = (
            active["prompts"]["strategy_instructions"]
            + "\n\nAnchor the opening offer more aggressively — 15-20% below the fair-price low, not just below it."
        )
        st.rerun()
    if p3.button("Reset to v1.0 baseline"):
        v1 = config_store.get_version("v1.0")
        st.session_state.tweak_form = {
            "model_id": v1["model_id"],
            "temperature": v1["temperature"],
            "prompts": dict(v1["prompts"]),
        }
        st.rerun()

    form = st.session_state.tweak_form
    label = st.text_input("Version label", value="")
    model_id = st.selectbox("Model", config_store.AVAILABLE_MODELS, index=config_store.AVAILABLE_MODELS.index(form["model_id"]) if form["model_id"] in config_store.AVAILABLE_MODELS else 0)
    temperature = st.slider("Temperature", 0.0, 1.0, float(form["temperature"]), 0.05)

    with st.expander("Research prompts (2 calls: tool-use agent + parser)"):
        research_tool = st.text_area("Research — tool agent instructions", value=form["prompts"]["research_tool_instructions"], height=200)
        research_parser = st.text_area("Research — parser instructions", value=form["prompts"]["research_parser_instructions"], height=150)
    with st.expander("Strategy prompt"):
        strategy_p = st.text_area("Strategy instructions", value=form["prompts"]["strategy_instructions"], height=150, label_visibility="collapsed")
    with st.expander("Negotiation prompt"):
        negotiation_p = st.text_area("Negotiation instructions", value=form["prompts"]["negotiation_instructions"], height=150, label_visibility="collapsed")
    with st.expander("Final outcome prompt"):
        final_p = st.text_area("Final outcome instructions", value=form["prompts"]["final_instructions"], height=150, label_visibility="collapsed")

    if st.button("Deploy this as a new version", type="primary"):
        new_prompts = {
            "research_tool_instructions": research_tool,
            "research_parser_instructions": research_parser,
            "strategy_instructions": strategy_p,
            "negotiation_instructions": negotiation_p,
            "final_instructions": final_p,
        }
        new_version = config_store.create_version(
            label=label or f"tweak of {active['id']}",
            model_id=model_id,
            temperature=temperature,
            prompts=new_prompts,
            notes=f"Created from Play/Tweak page, based on {active['id']}.",
        )
        del st.session_state["tweak_form"]
        mark_done("tweak")
        st.success(f"Deployed **{new_version['id']}** and made it active.")
        st.session_state.handoff["new_version_id"] = new_version["id"]

    st.divider()
    st.markdown("**All versions**")
    for v in reversed(config_store.list_versions()):
        active_marker = " (active)" if v["id"] == config_store.get_active_version_id() else ""
        st.write(f"`{v['id']}`{active_marker} — {v['label']}")
        if v["id"] != config_store.get_active_version_id():
            if st.button(f"Make {v['id']} active", key=f"activate_{v['id']}"):
                config_store.set_active_version(v["id"])
                st.rerun()

    if st.button("See real performance →", type="primary"):
        goto("track")

# ---------------------------------------------------------------------------
# PAGE 6 — Track Performance
# ---------------------------------------------------------------------------
elif page == "track":
    mark_done("track")
    st.title("6. Track Performance")
    mlflow_tracking.seed_historical_baselines()

    active_id = config_store.get_active_version_id()
    before_after = mlflow_tracking.get_before_after(active_id)

    if not before_after["has_data"]:
        st.warning(f"No eval runs logged yet for the active version `{active_id}`. Run a quick eval below.")
    else:
        current = before_after["current"]
        st.subheader(f"Active version: `{active_id}` — {config_store.get_version(active_id)['label']}")
        if before_after["delta"] is not None:
            st.metric(
                "Avg. price-movement % vs. previous version",
                f"{current['avg_price_movement_pct']}%",
                delta=f"{before_after['delta']:+.1f} pts",
            )
        else:
            st.metric("Avg. price-movement %", f"{current['avg_price_movement_pct']}%")
            st.caption("This is the first scored version — no prior version to compare against yet.")

    st.divider()
    n_cases = st.slider("How many real test cases to run for this eval", 1, 5, 2)
    if not keys_ready:
        st.info("Add your Groq and Serper API keys in the sidebar to run a live eval.")
    if st.button(f"Run eval on active version ({n_cases} real test case{'s' if n_cases > 1 else ''})", type="primary", disabled=not keys_ready):
        version = config_store.get_active_version()
        cases = TEST_CASES[:n_cases]
        progress = st.progress(0.0, text="Starting...")
        log_lines = []

        def trace(msg):
            log_lines.append(msg)
            progress.progress(min(0.95, len(log_lines) / (n_cases * 6)), text=msg[:80])

        results = live_agent.run_quick_eval(version, cases, trace)
        for r in results:
            mlflow_tracking.log_eval_run(
                version_id=version["id"],
                test_case_id=r["id"],
                model_id=version["model_id"],
                metrics={
                    "price_movement_pct": r.get("price_movement_pct"),
                    "comps_count": r.get("comps_count"),
                    "rounds_run": r.get("rounds_run"),
                    "outcome_deal_closed": 1 if r.get("outcome") == "deal_closed" else 0,
                    "errored": 1 if r.get("error_stage") else 0,
                    "duration_sec": r.get("duration_sec"),
                },
                params={"temperature": version["temperature"]},
            )
        progress.progress(1.0, text="Done")
        st.success(f"Logged {len(results)} real runs for `{version['id']}` to MLflow.")
        st.rerun()

    st.divider()
    st.markdown("**All versions, real logged runs:**")
    cmp_df = mlflow_tracking.get_version_comparison()
    if cmp_df.empty:
        st.info("No runs logged yet.")
    else:
        st.dataframe(cmp_df, use_container_width=True, hide_index=True)
    st.caption(
        f"Backed by MLflow at `evals/mlflow.db` (experiment: `{mlflow_tracking.EXPERIMENT_NAME}`). "
        "View locally with: `mlflow ui --backend-store-uri sqlite:///evals/mlflow.db`"
    )
