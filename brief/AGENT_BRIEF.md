# AGENT_BRIEF.md — OLX Negotiation Copilot

## 1. Problem Statement

Buyers on OLX in India routinely overpay because negotiating well takes market research and back-and-forth persistence most people don't have time for — they either accept the listed price or send one lowball message and give up after the first pushback. There's no tool today that researches a fair price for a specific listing, holds a disciplined multi-round negotiation, and knows when to walk away.

**This agent solves:** for one real OLX listing the user cares about, the agent researches a fair price, plans a negotiation strategy with an explicit walk-away line, and coaches the user turn-by-turn through the actual chat with the seller — ending in a single, clear outcome message.

## 2. User Persona

| Field | Detail |
|---|---|
| Name | The Value-Conscious OLX Buyer |
| Who | Urban Indian online shopper, 20s–40s, buys secondhand electronics/furniture/appliances on OLX a few times a year |
| Context | Has found one specific listing they want, but the asking price feels high and they don't know how much room the seller actually has |
| Tech comfort | Comfortable with chat apps and copy-pasting between apps; not a developer |
| Goal | Get the item at a fair price without spending hours researching comps or feeling awkward haggling |
| Frustration | Either overpays by accepting the first price, or lowballs once, gets ignored, and gives up |

## 2a. Job-to-be-Done

> **When I** find a secondhand item on OLX I want to buy but the price feels negotiable, **I want to** have an agent research what it's really worth and coach me through a real negotiation with the seller, **so I can** get a fair price without guessing or losing my nerve halfway through.

## 3. Input / Output Specification

**Inputs**

| Input | Type | Example | Required |
|---|---|---|---|
| Listing details, pasted as text | string | pasted title, price, and description, e.g. "Samsung Galaxy S21, ₹18,000, 1 year old, good condition" | Yes |
| Buyer's max budget | integer (₹) | 14000 | Yes |
| Urgency | enum (Low / Medium / High) | "Medium — want it within a week" | Yes |
| Dealbreakers / must-haves | string | "must have original box and bill" | No |
| Seller's message (per turn, relayed by user) | string | "I can do ₹13,800, final" | Yes, once negotiation starts |

**Outputs**

| Output | Format | Description |
|---|---|---|
| Fair-price range | short text + number range | e.g. "₹13,500–15,000 based on 6 comparable listings" |
| Negotiation strategy | short structured text | opening anchor, concession ladder, walk-away price, shown to user before first message is sent |
| Suggested message (per turn) | plain text | exact message for the user to paste into the real OLX chat |
| Final outcome message | structured text (see Section 4, step 8) | deal price / walk-away, savings vs. ask, reason for stopping, next action |

*A bare OLX link isn't accepted as input — OLX blocks automated fetching, so the agent can't open a link on the user's behalf. This was originally scoped as "link or text" but corrected to text-only after a live-testing bug surfaced the gap between the two (see `README.md`, Shipping & reliability notes).*

## 4. Step-by-Step Workflow (Plain English)

1. User pastes the listing's title, price, and description as text into the web chat UI.
2. Agent extracts listing details: asking price, condition, description, how long it's been posted.
3. Agent searches for 5–10 comparable OLX listings to build a fair-price range, noting signals like "this one's been up 18 days" (room to negotiate) or "priced below comps already" (little room).
4. Agent asks the user 2–3 quick questions: max budget, urgency, any dealbreakers.
5. Agent proposes a negotiation strategy out loud — opening offer, how much to concede per round, and a walk-away price — and asks the user to confirm before proceeding.
6. Agent gives the user the first message to send; user copies it into the real OLX chat with the seller.
7. User pastes the seller's real reply back into the agent's chat; agent reads it, updates its read on how flexible the seller seems, and decides: counter, hold, accept, or walk away — then gives the user the next message to send. This repeats for as many rounds as the real conversation takes.
8. When the seller accepts, refuses to move further, or goes silent, the agent sends a final message stating the outcome: deal price (or best offer if walking away), savings vs. the original ask, why it stopped there, and what the user should do next.
9. The session ends there. In this version, each negotiation is independent — no lesson carries over to the next one. (A cross-session memory layer that compounds lessons across negotiations was part of the original concept but is explicitly out of scope for v1, per Section 6's single-session constraint; see Section 10 for the upgrade path.)

## 5. Success Metrics

| Metric | Target | How to Measure |
|---|---|---|
| Price improvement | Average ≥10% off original asking price on closed deals | (Ask price − final price) / ask price, across demo runs |
| Negotiation turns to resolution | ≤5 rounds to close or walk away | Count of buyer↔seller message pairs per session |
| Strategy transparency | User can restate the walk-away price and why before sending the first message | Manual check during demo / user testing |
| Reasoning visibility | Every agent turn shows what changed in its read of the seller before the next move | Manual review of transcripts |
| Reviewer comprehension (demo-specific) | A reviewer watching one full session can explain, unprompted, why the agent stopped where it did | Demo walkthrough feedback |

## 6. Constraints & Assumptions

**Constraints**
- Free/cheap to build: no paid scraping or data services — market research relies on public, non-authenticated OLX search/listing pages plus general web search.
- No direct OLX account automation — the agent never logs into or acts as the user's OLX account; all outbound messages are relayed by the user, by design (see Section 2, interaction mode decision).
- Single listing, single seller, single buyer per session — no multi-vendor parallel negotiation in this version.
- English/Hinglish text negotiation only — no voice or regional-language support.

**Assumptions**
- The user is willing to manually copy-paste messages between the agent and the real OLX chat for each round.
- Enough comparable listings exist publicly for the item category to build a meaningful fair-price range (works best for common categories like electronics, furniture, appliances; breaks down for one-of-a-kind items).
- The seller is a real, responsive individual who will engage in back-and-forth (not a dealer using a fixed-price bot).
- Public OLX listing/search pages remain accessible for read-only research without requiring login.

## 7. Contra-Indicators (When NOT to Use This Agent)

| Situation | Why it's unfit | Better alternative |
|---|---|---|
| Buying from a dealer/business listing with fixed pricing | No real negotiation possible; agent's strategy has nothing to work against | Just buy directly, or compare listings manually |
| Rare/unique item with no comparable listings | Fair-price research has nothing to anchor to; agent's range would be a guess | Ask a category expert or accept price discovery will be manual |
| Time-critical purchase (need it today) | Multi-round negotiation takes hours to days of back-and-forth; agent is optimizing price, not speed | Buy at asking price or search for immediate-pickup listings |
| High-stakes or high-value item (e.g. a car, property) | Financial and legal risk is too high for a demo-grade agent; requires inspection, paperwork, and real expertise beyond price negotiation | Use a professional broker/inspector-backed platform |
| Seller requires an in-person or voice-call negotiation | Agent only reasons over text messages relayed by the user; it can't handle live voice/in-person haggling | Negotiate directly, or use the agent only for pre-visit price research |
| User wants a fully autonomous "set and forget" negotiation | This version deliberately keeps the user in the loop for every message sent (see interaction-mode decision) | Would require the "fully automated" build path, not this brief |

## 8. Data Grounding & Freshness

| Dimension | Detail |
|---|---|
| Data source | Public OLX search/listing pages (read-only, no login) plus general web search for category price context |
| Knowledge cutoff | LLM's training data is not used for pricing — all price figures must come from live comp lookups performed during the session, not model memory |
| Grounding method | Live web search/browse for comparable listings at negotiation start; no persistent database in this version |
| Freshness risk | Medium — OLX listings and prices change daily/weekly; a comp lookup is only as fresh as the moment it's run, and stale comps could mislead the strategy |
| Mitigation | Agent always states how many comps it found and when the price range is based on ("as of this search"), so the user can sanity-check before committing to a strategy |
| Upgrade path | v2 could periodically refresh comps mid-negotiation for long-running threads, and build the persistent "wiki" of category-level negotiation patterns described in the broader concept, so price ranges and tactics compound across sessions instead of resetting each time |

## 9. Top 3 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Comp research returns too few or irrelevant listings, producing a misleading fair-price range | Medium | High | Agent must show its comps and confidence level explicitly, and flag low-confidence ranges (e.g. "only 2 comps found, treat this range as rough") rather than presenting a number as authoritative |
| User relay breaks the illusion of a smooth agent (copy-paste friction, delays waiting for seller replies, transcription errors) | High | Medium | Keep the workflow's UI simple (one-click copy for suggested messages, one paste box for seller replies); frame this explicitly as "you're the hands, I'm the strategist" so the friction is expected, not a bug |
| Demo audience mistakes the human-in-the-loop design for a limitation rather than a deliberate, safer architecture choice | Medium | Medium | Brief and demo narration should state upfront *why* this path was chosen (no ToS/account-automation risk) and name the autonomous upgrade path as a known next step, not an oversight |

## 10. Learning Objectives (PM Lens)

- Demonstrates **tool-augmented grounding**: the agent's price claims come from live retrieval (comp search), not from the model's own priors — a concrete illustration of why grounding matters for any agent making real-world numeric claims.
- Makes **multi-turn state tracking** tangible: the agent has to carry its walk-away price, concession ladder, and read of seller flexibility across rounds — a single LLM call can't do this, since each turn depends on what happened in the previous one.
- Key architectural insight: **this is a true agent, not a prompt chain** — the number of turns isn't fixed in advance, and each response is a genuine decision (counter/hold/accept/walk away) conditioned on unscripted human input, not a predetermined script being filled in.
- The **human-in-the-loop relay** is itself a teaching point: it shows that "agentic" is about the reasoning loop, not about full autonomy — a deliberate scope cut (no OLX account automation) that keeps the demo safe without weakening the agentic core.
- Natural next-level upgrade: replace the manual relay with direct channel access (e.g. WhatsApp, where many OLX sellers list a phone number) for full autonomy, and add the persistent cross-session "wiki" layer so lessons from one negotiation compound into the next — turning a single-session agent into a self-improving one.

> **Key insight for this project:** the hard part of "agentic negotiation" isn't generating persuasive messages — it's disciplined state-tracking (a walk-away price that's actually respected) and reacting to a real counterpart's unscripted response, which is exactly what separates this from a chatbot that just drafts a haggling message once.
