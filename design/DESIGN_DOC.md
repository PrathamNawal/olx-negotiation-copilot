# DESIGN_DOC.md — OLX Negotiation Copilot

Framework: **Agno** (Python agent framework) · Stack: **Python + Streamlit** · Research tool: **live web search** · Model: recommended below

## 1. Agent Architecture Classification

| Dimension | This Agent | Why |
|---|---|---|
| Pattern | ReAct loop (Level 3) | Each negotiation round is a genuine decision conditioned on an unscripted human (the seller) relayed through the user — the number of rounds isn't known in advance, so it can't be a fixed chain |
| Memory | In-context / session state only | One listing, one seller, one session — the agent only needs to remember its own walk-away price, ladder, and round count for the duration of this negotiation, not across sessions |
| Tools | Web search (comp research) | Grounds the fair-price range in live, real listings instead of the model's own priors |
| Autonomy level | Level 3 — ReAct loop | Matches the domain: reason → decide to search or respond → observe seller's reply → repeat, until a defined stop condition |
| Upgrade path | Level 4 — multi-agent | Needed only if scope expands to negotiating several sellers in parallel (an orchestrator + one negotiator agent per seller); not needed for a single listing |

## 2. Architecture Decision

**What is the minimum autonomy level needed to solve this problem?** Level 3.

| Level | Pattern | Description | This agent? |
|---|---|---|---|
| 1 | Single LLM call | One prompt in, one response out | ❌ |
| 2 | Prompt chain | Sequential calls, output feeds next | ❌ |
| 3 | ReAct loop | LLM reasons, picks tool, observes, repeats | ✅ |
| 4 | Multi-agent | Orchestrator delegates to specialists | ❌ |

- **Why this level is right:** Negotiation is a loop of unknown length reacting to an external party the agent doesn't control. Round 1's seller reply might be a firm rejection, a counter-offer, or silence — the agent has to reason fresh each time and decide whether to call the search tool again, hold its line, concede, accept, or walk away. That's the definition of a ReAct loop, not a pipeline.
- **What would require going higher:** If the product expanded to running several sellers against each other simultaneously (multi-vendor negotiation, as sketched in the original concept), that naturally splits into an orchestrator agent plus one negotiator agent per seller thread — a Level 4 problem. Single-listing v1 doesn't need it.
- **What complexity this avoids:** No agent-to-agent handoff logic, no orchestrator, and no persistent cross-session memory system (the "wiki" of compounding negotiation patterns from the original concept). All three are real, named upgrade paths — just not required to prove the agentic loop works for one negotiation.

## 3. Workflow Diagram

```
┌─────────────────────────┐
│ USER INPUT               │
│ Pastes OLX listing        │
│ (URL or text)             │
└────────────┬─────────────┘
             ▼
┌─────────────────────────────────┐
│ AGENT: Parse listing              │
│ Extract price, condition,         │
│ description, days listed          │
└────────────┬─────────────────────┘
             ▼
┌─────────────────────────────────┐        ┌───────────────────────┐
│ AGENT: Call web search tool       │──────▶│ TOOL: Web Search        │
│ Query for comparable listings     │◀──────│ Returns 5-10 comps      │
└────────────┬─────────────────────┘        └───────────────────────┘
             ▼
┌─────────────────────────────────┐
│ AGENT OUTPUT: Fair-price range     │
│ + confidence note (# comps found,  │
│ how stale the ask is)              │
└────────────┬─────────────────────┘
             ▼
┌─────────────────────────┐
│ USER INPUT                │
│ Answers: budget, urgency, │
│ dealbreakers               │
└────────────┬─────────────┘
             ▼
┌─────────────────────────────────┐
│ AGENT OUTPUT: Negotiation strategy │
│ Opening anchor, concession ladder, │
│ walk-away price                    │
└────────────┬─────────────────────┘
             ▼
┌─────────────────────────┐
│ USER ACTION (confirms)    │
│ Approves strategy          │
└────────────┬─────────────┘
             ▼
      ┌──────────────────────────────────────────────┐
      │  NEGOTIATION LOOP (repeats N rounds)            │
      │                                                  │
      │  ┌─────────────────────────┐                    │
      │  │ AGENT OUTPUT: suggested   │                    │
      │  │ message for this round    │                    │
      │  └────────────┬─────────────┘                    │
      │               ▼                                  │
      │  ┌─────────────────────────┐                    │
      │  │ USER ACTION (outside app) │                    │
      │  │ Pastes message into real   │                    │
      │  │ OLX chat with seller       │                    │
      │  └────────────┬─────────────┘                    │
      │               ▼                                  │
      │  ┌─────────────────────────┐                    │
      │  │ USER INPUT                 │                    │
      │  │ Pastes seller's real reply │                    │
      │  └────────────┬─────────────┘                    │
      │               ▼                                  │
      │  ┌─────────────────────────────────┐            │
      │  │ AGENT: Reason over reply           │            │
      │  │ Update read of seller flexibility, │            │
      │  │ decide: counter / hold / accept /  │            │
      │  │ walk away                          │            │
      │  └────────────┬─────────────────────┘            │
      │               ▼                                  │
      │      Stop condition met? ──No──▶ (loop repeats)   │
      │               │Yes                                │
      └───────────────┼──────────────────────────────────┘
                       ▼
┌─────────────────────────────────┐
│ AGENT OUTPUT: Final outcome message│
│ Outcome / price / reason / next    │
│ action (fixed schema)              │
└────────────┬─────────────────────┘
             ▼
┌─────────────────────────┐
│ SESSION LOG (local)       │
│ Category + tactic used +  │
│ rounds + result            │
│ (not persisted across      │
│ sessions in v1)            │
└─────────────────────────┘
```

## 4. Agent Configuration Sheet

### 4a. Model Parameters

| Parameter | Value | Rationale |
|---|---|---|
| Model | Claude Haiku (latest small/fast tier) | Negotiation-turn reasoning is bounded and structured (read a reply, update a ladder, pick one of four moves) — it doesn't need frontier reasoning, and a small model keeps the "free/cheap to build" constraint real rather than aspirational. Upgrade to Sonnet if testing shows it losing track of the walk-away price or misreading seller tone. |
| Temperature | 0.4 | Low enough to keep numeric state (walk-away price, ladder) consistent turn to turn; not 0, because the suggested messages should read like a person negotiating, not a robotic template repeated with different numbers. |
| Max tokens | 700 per turn | Outputs are short by design (one strategy note or one message or one final outcome) — this is a ceiling to catch runaway generation, not a target. |
| Timeout | 30s | Generous enough for one reasoning turn plus a tool call, tight enough that the Streamlit UI doesn't feel frozen. |
| Top-p | Default | Temperature is the primary creativity control here; no reason to also tune top-p for this task. |
| Frequency penalty | Not set | Not needed at this output length; would only matter if the agent started repeating stock phrases across many rounds, which can be caught in testing instead. |

> **When to change temperature:** Lower it (toward 0.2) if testing shows the agent drifting off its stated walk-away price or inventing price figures not from a search result — this is a state-discipline problem, not a creativity one. Raise it slightly (toward 0.6) only if the suggested messages start reading identically round to round in a way that feels obviously templated to the user relaying them.

### 4b. Prompt Architecture

**System Prompt Role:** Defines the agent's identity as a negotiation strategist, the tools it may use, the hard rule that price claims must trace to a search result, and the fixed output schema for the final outcome message.

```
You are a negotiation strategist helping a buyer negotiate the price of
one specific OLX listing. You do not talk to the seller directly — the
user relays your messages and reports the seller's real replies back to you.

Rules:
- Never state a price comparison or "fair price" claim that isn't backed
  by a search result returned in this session.
- Track and respect the agreed walk-away price. Never suggest accepting
  below it without explicitly flagging that you are breaking the rule
  and asking the user to confirm.
- Each response is exactly one of: [research summary] / [strategy
  proposal] / [next message to send] / [final outcome].
- The final outcome message must always follow this schema:
  Outcome (Deal closed / Walked away) | Final price | Savings vs.
  original ask | Reason negotiation stopped | Next action for the user.
```

**User Prompt Role:** Carries the current negotiation state and the latest input — either the listing itself (turn 1), the user's budget/urgency/dealbreakers, strategy confirmation, or the seller's latest relayed reply.

```
Listing: {listing_details}
Round: {round_number}
Current ladder position: {ladder_state}
Walk-away price: {walkaway_price}
Latest seller reply (if any): {seller_reply}
```

**Critical constraint:** The final outcome message must always emit the five fixed fields in the schema above, in that structure — the session log and the demo's "reviewer can restate why it stopped" success metric both depend on that shape being reliable, not just readable.

### 4c. Memory Configuration

| Memory Type | Used? | Notes |
|---|---|---|
| In-context (conversation history) | Yes | Needed within a session to track round number, ladder position, and walk-away price — this is the agent's working memory for the negotiation |
| Vector / RAG | No | No knowledge base to retrieve from in v1; comps come from a live tool call, not a stored index |
| External DB | No | Session ends when the negotiation ends; nothing persists automatically |
| Session state | Yes | Streamlit session state holds the structured negotiation state (target price, ladder, walk-away price, comps found) across the app's reruns within one session |

**Upgrade path:** Adding an external DB (plus eventually vector search) is what would unlock the original concept's "wiki" layer — compounding, category-level negotiation patterns (e.g. "electronics sellers listed >2 weeks concede ~12-15% by round 3") that persist and improve across sessions and, potentially, across users.

### 4d. Tools Configuration

| Tool | Used? | Notes |
|---|---|---|
| Web search | Yes | Called once at session start to find comparable listings; the only tool in v1 |
| OLX account / browser automation | No | Deliberately excluded — the brief's interaction-mode decision keeps the user as the relay to avoid ToS/automation risk |
| Persistent wiki read/write | No | Deferred; v1 logs the outcome locally per session only, doesn't write to or read from a shared knowledge store |

**Upgrade path:** The highest-value next tool is a messaging channel (e.g. WhatsApp Business API, since many OLX sellers list a phone number) that would let the agent send and receive messages directly — the step that turns this from human-in-the-loop into fully autonomous, as named in the brief.

## 5. Data Flow & Security Notes

- LLM and search API keys live in Streamlit secrets / environment variables, never in client-side code or committed to the repo. If leaked, the risk is unauthorized API usage charges, not user data exposure (no OLX credentials are ever handled by this agent).
- Data sent to the LLM provider: the listing text, the user's stated budget/urgency/dealbreakers, and the seller's relayed reply text. No OLX login, no payment info, no seller contact details beyond what's visible in the pasted listing/messages.
- Data sent to the search provider: query terms derived from the listing (category, condition, approximate price) — not the user's personal budget or identity.
- What's logged: the session transcript and final outcome are held in Streamlit session state for the duration of the session. Nothing is written to disk or a database in v1 unless the user explicitly exports it — if that export feature is added, it should be scoped to the negotiation content only, not any incidental personal detail the seller shared.
- Third-party retention: both the LLM provider and the search provider may retain query/API logs per their own policies — this is outside this agent's control and should be disclosed to any demo audience, not glossed over.

## 6. Data Grounding & Freshness

| Dimension | Detail |
|---|---|
| Data source | Live web search results, fetched once at the start of each session |
| Knowledge cutoff | The model's training data must never be the source of a price claim — enforced by the system-prompt rule that every price statement must trace to a search result returned this session |
| Grounding method | Ad hoc web search per session (not a stored/vector index) |
| Freshness risk | Medium — comps are fetched once; if a negotiation stretches over several days (the seller goes quiet, user comes back later), the price range could be stale by the time it's used |
| Mitigation | The agent states how many comps it found and timestamps the range ("as of this search") so the user can judge staleness themselves; recommend re-running research if a session resumes after ~48 hours |
| Upgrade path | Periodic re-search for long-running sessions, and eventually the persistent cross-session wiki so price/tactic knowledge compounds instead of resetting every negotiation |

## 7. Eval Success Definition (Pre-Build)

| Criterion | What "good" looks like |
|---|---|
| Comp grounding | Every price claim in the session traces to a specific search result actually returned that session — zero invented figures |
| Walk-away discipline | The agent never proposes accepting below the agreed walk-away price without an explicit flag and user confirmation |
| Turn relevance | Each suggested message directly responds to the content of the seller's actual last reply — not a generic template reused regardless of what the seller said |
| Termination correctness | The final outcome message is issued only when one of the three defined stop conditions (accepted / ladder exhausted / user ends it) is actually met — never premature, never stuck in an endless loop |
| Outcome completeness | The final message always contains all five schema fields: outcome, price, savings vs. ask, reason, next action |
| Strategy transparency | The user sees and explicitly confirms the walk-away price and ladder before the first message is ever sent |

**Minimum bar for v1:** the agent completes one full listing-to-outcome cycle without crashing, grounds its fair-price range in at least one live search result, never silently breaks the user-confirmed walk-away price, and produces a final message matching the required schema.

## 8. Excalidraw Diagram Notes

- **Colour coding:** blue = user input (typed into the app), grey = user action outside the app (relaying a message into real OLX chat), yellow = agent reasoning/LLM call, green = tool call (web search), purple = agent output/final message.
- **Arrow labels:** label every arrow into/out of the negotiation loop with what's being passed — "suggested message," "seller's real reply," "updated ladder state" — so a viewer can trace state without reading the boxes closely.
- **Grouping:** group into four visual clusters — (1) Research phase: parse listing → search tool → fair-price range; (2) Strategy phase: ask questions → propose ladder/walk-away → user confirms; (3) Negotiation loop: the repeating round cycle, drawn as a literal loop shape with a "repeats N rounds" label; (4) Termination: stop-condition check → final outcome message → session log.
- **Special annotations:** mark the negotiation loop (cluster 3) as "critical path — this is the agentic core, not a script"; mark the final outcome message box as "fixed schema — this is where downstream logging/parsing breaks if the format drifts"; mark the grey "relay to real OLX chat" step as "deliberate scope boundary — see Section 4d, no account automation in v1."
