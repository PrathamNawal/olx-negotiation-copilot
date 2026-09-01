# OLX Negotiation Copilot

A Level-3 ReAct agent (Agno + Groq) that researches a fair price for one
real OLX listing, proposes a negotiation strategy, and coaches you
round-by-round through the real negotiation — ending in a fixed-schema
outcome message. See `brief/AGENT_BRIEF.md` and `design/DESIGN_DOC.md` for
the full product and architecture rationale, `evals/EVAL_SCORECARD.md` for
the Phase 4 eval results, and `dashboard/` for the PM dashboard (below).

## Setup

```bash
cd app
pip install -r ../requirements.txt
export GROQ_API_KEY=your_key_here
export SERPER_API_KEY=your_key_here  # google.serper.dev — see note below
streamlit run app.py
```

**Verified working end-to-end** (research → strategy → negotiation round →
final outcome) on Groq's `openai/gpt-oss-20b`. `openai/gpt-oss-120b` also
verified working but has a low free-tier daily token quota that testing
itself exhausted; `llama-3.3-70b-versatile` isn't available on the key this
was built with. Override with `GROQ_MODEL_ID` if you want to try another.

## How it works

1. Paste a real OLX listing → agent searches the web for comps and proposes
   a fair-price range.
2. Tell it your budget, urgency, and dealbreakers → agent proposes an
   opening offer, concession ladder, and walk-away price. You confirm before
   anything is sent.
3. For each round: copy the agent's suggested message into the real OLX
   chat, paste the seller's real reply back in. The agent decides to
   counter, hold, accept, or walk away based on what the seller actually
   said.
4. The agent's final message states the outcome, final price, savings vs.
   the original ask, why it stopped, and what to do next.

## Scope notes (see design doc for full rationale)

- The agent never logs into or automates your OLX account — you're the
  relay between it and the real chat, by design (no ToS/automation risk).
- Nothing is persisted across sessions in v1 — each negotiation starts
  fresh. The cross-negotiation "learns over time" wiki layer is a named
  upgrade path, not built here yet.
- Web search is the only tool the agent has. Originally built on free
  scraped DuckDuckGo search per the design doc's "free/cheap" constraint;
  switched to the Serper API (has a free tier, needs an API key) after live
  testing showed this build environment's network egress to every scraped
  search backend (DuckDuckGo, Bing, Brave, Mojeek, Yahoo, Google via ddgs)
  was unreliable — timeouts, empty results, and hangs traced to the sandbox's
  own egress proxy, not the search providers. Worth re-testing free scraped
  search if you deploy somewhere with normal network egress.

## PM Dashboard

```bash
cd dashboard
pip install -r ../requirements.txt   # now includes mlflow
streamlit run app.py
```

A guided 6-page walkthrough (What is this? → How it works → Try it, Human →
Try it, Agent → Play/Tweak → Track Performance) around the real agent above.
Editing a prompt or model on the Tweak page creates a new, real version
(`dashboard/config_store.py`, seeded from the actual prompt text in
`app/agent.py` — nothing here is a placeholder). Every run on Try-it-Agent
and every eval you trigger on Track Performance is a real Groq+Serper call
using your own API keys (BYOK — never an embedded owner key). Version
comparison is backed by the same MLflow database the Phase 4 eval harness
wrote to (`evals/mlflow.db`) — the 5 real eval runs from
`evals/EVAL_SCORECARD.md` show up as v1.0's baseline automatically. Primary
comparison metric: price-movement % vs. asking price on closed deals.

Verified with a real Playwright click-through (not just an HTTP 200 check):
submitted a human guess, ran the live agent, deployed a new tweaked version,
ran a real eval on it, and confirmed the before/after delta on Track
Performance updated from genuine logged data.

## Reliability notes from live testing

A few real Groq/model quirks found and worked around, worth knowing if you
extend this:

- **Groq rejects combining structured JSON output with tool calling** in
  one call. That's why research runs as two agent calls (`agent.py`'s
  `run_research`): one with tools and free-text output, one with no tools
  and a fixed schema to structure the first call's findings.
- **The model sometimes skips calling the search tool** and just answers
  from the listing text alone, silently. `run_research` detects this by
  checking the run's actual recorded tool calls (not the text) and retries
  once with an explicit nudge if the tool wasn't called. Forcing
  `tool_choice="required"` does NOT fix this — Groq then also requires a
  tool call on the model's final synthesis turn, which breaks it worse.
- **Structured output occasionally comes back malformed** (truncated JSON,
  rate-limit errors as content, garbled/duplicated fields) instead of
  raising cleanly. Every phase goes through `_run_structured`, which
  detects a non-schema response and retries before failing loudly.
- **Token budgets need headroom for verbose steps.** The research stage
  writes up to 10 comps before structuring them — both the tool-use call and
  the parser call need a noticeably higher `max_tokens` than the other
  phases, or output gets truncated mid-JSON and fails to parse.

