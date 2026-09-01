# Eval Scorecard — OLX Negotiation Copilot
> Phase 4: Full | OLX Negotiation Copilot
> Status: FULL — scored on real outputs (live Groq `openai/gpt-oss-20b` + Serper calls, no mocked agent output)

Every result below came from an actual run of `evals/run_eval.py` against the real 4-phase pipeline
(`app/agent.py`'s `run_research` → `run_strategy` → `run_negotiation_move` → `run_final_outcome`).
Seller replies are scripted test fixtures (the same role a QA tester's "here's what the other side
said" input plays) — everything downstream of them is a genuine model+tool call. Raw output for every
test case is in `evals/eval_results.json`; every run is also logged as an MLflow run in
`evals/mlflow.db` (see note at the end).

---

## Section 1 — Test Case Library

| Test ID | Listing | Budget | Urgency | Dealbreakers | Scenario label |
|---|---|---|---|---|---|
| TC-01 | iPhone 13 Pro Max Jade Green 256GB, ask ₹44,444 | ₹40,000 | Medium | none | Happy path |
| TC-02 | "Samsung phone, ₹8000, ok condition" | ₹6,500 | Low | none | Edge: minimal input |
| TC-03 | Sony A7 III + kit lens + accessories, ask ₹98,000 | ₹90,000 | High | must include bill/warranty; no COD | Edge: maximal / complex input |
| TC-04 | Yamaha RD350 1985 project bike (non-running), ask ₹1,85,000 | ₹1,50,000 | Low | clear RC, no theft case | Niche / low-comp item |
| TC-05 | OnePlus 11R, Hinglish + emoji listing, "26k nego" | ₹20,000 | High | COD only | Stress test: Hinglish, messy formatting, aggressive seller |

---

## Section 2 — Evaluation Rubric

### Category 1: Format & Schema Compliance (25 points)
*Does every phase return valid structured output, including the fixed final-outcome schema the design doc treats as a hard constraint?*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Research output validates to `ResearchResult` (no raw-string fallback) | 5 | 5 | 5 | 5 | 5 | 5 |
| Strategy output validates to `StrategyProposal` | 5 | 5 | 5 | 5 | 5 | 5 |
| Each negotiation round validates to `NegotiationMove` | 5 | 5 | 5 | 5 | 5 | 5 |
| Final outcome reached, matches fixed `FinalOutcome` schema, all fields populated | 10 | 10 | 10 | **0** | 10 | 10 |
| **Subtotal** | /25 | **25** | **25** | **15** | **25** | **25** |

### Category 2: Grounding & Research Quality (25 points)
*Are the comps actually about the item being sold, and does the confidence note honestly reflect comp quality?*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Comps are relevant / title-matched to the exact listing | 10 | 10 | **1** | 8 | 6 | 10 |
| Confidence note honestly reflects actual comp quality | 10 | 9 | **3** | 9 | 10 | 9 |
| No garbled / URL / tracking-string `source_note` | 5 | 5 | 5 | 5 | 5 | 5 |
| **Subtotal** | /25 | **24** | **9** | **22** | **21** | **24** |

### Category 3: Negotiation Discipline (30 points)
*Does the agent stay inside its own walk-away price and react to what the seller actually said?*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Opening offer sensibly anchored (below fair range, within budget) | 5 | 5 | 5 | 5 | 5 | 5 |
| Walk-away price never exceeded by any move | 10 | 10 | 10 | 10 | 10 | 10 |
| `breaks_walkaway` flag set correctly | 5 | 5 | 5 | 5 | 5 | 5 |
| Decision is specific and reactive to the seller's actual words, not generic | 10 | 10 | 9 | 9 | 10 | 10 |
| **Subtotal** | /30 | **30** | **29** | **29** | **30** | **30** |

### Category 4: Edge Case & Robustness Handling (20 points)
*Each check targets the TC it was designed to stress; N/A cells pass through (not applicable ≠ failed).*

| Check | Points | TC-01 | TC-02 | TC-03 | TC-04 | TC-05 |
|---|---|---|---|---|---|---|
| Minimal/sparse input still produced usable structured output | 5 | N/A | **3** | N/A | N/A | N/A |
| Hinglish / emoji / messy formatting parsed without breaking | 5 | N/A | N/A | N/A | N/A | 5 |
| Low-comp/niche item triggered an honest low-confidence signal | 5 | N/A | N/A | N/A | 5 | N/A |
| Transient Groq errors (rate limit / JSON-validate) retried and recovered | 5 | 5 (recovered from `json_validate_failed`) | N/A | N/A | 5 (recovered from TPM rate limit) | N/A |
| **Subtotal** (N/A cells scored as pass-through) | /20 | **20** | **18** | **20** | **20** | **20** |

---

## Section 3 — Scoring Summary

| Test Case | Format /25 | Grounding /25 | Discipline /30 | Robustness /20 | Total /100 | Pass? |
|---|---|---|---|---|---|---|
| TC-01 | 25 | 24 | 30 | 20 | **99** | ✓ |
| TC-02 | 25 | 9 | 29 | 18 | **81** | ✗ (category floor) |
| TC-03 | 15 | 22 | 29 | 20 | **86** | ✓ |
| TC-04 | 25 | 21 | 30 | 20 | **96** | ✓ |
| TC-05 | 25 | 24 | 30 | 20 | **99** | ✓ |
| **Average** | 23.0 | 20.0 | 29.6 | 19.6 | **92.2** | |

**Pass threshold:** 70/100 overall, **and** no single category below 50% of its max.

TC-02 clears the overall bar (81/100) but **fails the category floor** — Grounding & Research Quality
landed at 9/25 (36%), because the search/parse pipeline accepted comps that were not actually about a
Samsung phone (see Section 4, Failure #1). Per this scorecard's own rule, TC-02 is a fail despite the
high total score — the total alone would have hidden a real, load-bearing problem.

---

## Section 4 — Known Failure Modes

| Failure | Trigger | Impact | Fix |
|---|---|---|---|
| Sparse-input comps are accepted without a title-relevance check | Listing text with no brand/model (TC-02: "Samsung phone, ₹8000") | Comps like "₹92,000" / "₹1,24,999" with no real title got treated as valid; strategy was built on ungrounded numbers while the confidence note still said "moderate confidence" | Add a relevance check in the research parser prompt: reject a search hit as a comp unless its title shares a keyword with the listing; force `confidence_note` to explicitly say "low — listing lacks brand/model" when the input itself is under ~15 words |
| Negotiation can outlast a short round budget when the seller lands just above walk-away | Seller's counter sits within one ladder-step of the walk-away price (TC-03: seller at ₹91,000 vs. walk-away ₹90,000) | Agent worked up its own ladder one increment per round (₹78k→₹82k→₹86k) instead of jumping to the walk-away price when the gap was small; needed 3+ rounds to plausibly resolve, more than this eval's 2-round budget | Add a rule (code, not just prompt wording): if the seller's ask is within one ladder-increment of walk-away, counter at the walk-away price directly instead of the next ladder step |
| Transient Groq errors surfaced in real runs | Any LLM call; observed on 2 of 5 test cases (`json_validate_failed` on TC-01's research stage, TPM rate limit on TC-04) | Both recovered via existing retry logic with no crash, but added real latency — runs ranged 57–80s | No functional fix needed; consider a distinct "retrying, one moment…" spinner state so a long pause doesn't read as a hang |
| `message_to_seller` is blank on `accept`/`walk_away` actions | Any negotiation round that ends in accept or walk-away | Transcript renders an awkward trailing line, e.g. "Round 1 decision — accept: " | Either drop the trailing "action: message" format when the message is empty, or have the prompt supply a short closing line even on accept/walk-away |
| `breaks_walkaway=True` never fired in this batch | None of the 5 scripted seller replies actually baited a move past the walk-away price | The design doc's "silently breaking the walk-away price" warning in `app.py` is unverified by this eval round — it may work, but there's no evidence yet | Add a 6th, adversarial test case whose seller reply is specifically designed to tempt the model over its own walk-away, to confirm the flag and the UI warning both fire |
| Confidence note and numeric range can disagree for niche items with disjoint market segments | Item where the closest available comps are technically title-matched but reflect a different condition/segment (TC-04: "non-running project bike" comps skewed toward restored/collector prices) | `confidence_note` correctly flagged "sparse comps, some mis-listed or new-bike prices" (a real strength), but `fair_price_low`/`fair_price_high` (₹150k–200k) weren't adjusted down to reflect that caveat — the qualitative flag and the quantitative range are inconsistent | Prompt the research parser to lower `fair_price_high` (or widen `confidence_note`'s caveat) whenever it flags comps as mismatched, rather than leaving the numeric range untouched |

---

## Section 5 — Prompt Iteration Log

| Version | Change Made | Why | Score Before | Score After |
|---|---|---|---|---|
| v1.0 | Initial 4-phase prompt set (research tool agent, research parser, strategy, negotiation, final outcome) as shipped in `app/agent.py` | Baseline — first fully working end-to-end build | — | 92.2/100 (this eval) |
| v1.1 | *(planned)* Add title-relevance check + low-detail-input confidence downgrade to research parser prompt | Fix TC-02's category-floor failure (Failure #1) | 92.2/100 | *(not yet run)* |
| v1.2 | *(planned)* Add walk-away-proximity snap rule to negotiation logic | Fix TC-03's non-termination (Failure #2) | — | *(not yet run)* |

---

## Section 6 — PM Reflection

- **Most common failure mode:** Grounding quality is only as good as the listing text the user provides — a sparse, brand/model-free input (TC-02) makes the search agent return comps that aren't really about the item, and the agent doesn't yet catch its own bad grounding before reporting "moderate confidence."
- **Worst-performing test case:** TC-02 (Edge: minimal input) — it passed every discipline and format check, but the whole strategy was quietly built on comps unrelated to a Samsung phone. This is exactly the kind of failure a total score can hide and a category floor is meant to catch.
- **Single biggest prompt improvement:** Teaching the research parser to check comp-title relevance against the listing before accepting it, and to be honest about low confidence when the input itself is thin. This is a pure prompt change — no new tool or architecture needed.
- **What requires an architecture change to fix:** Two things can't be reliably fixed by prompt wording alone. (1) The walk-away-proximity pacing issue (TC-03) needs a small code-level rule, since asking the model to "notice when the gap is small" through prose is exactly the kind of numeric-threshold judgment LLMs are inconsistent at. (2) Confirming `breaks_walkaway=True` actually fires needs either a deliberately adversarial eval case or a direct unit test on `run_negotiation_move` with a synthetic over-budget seller reply — the current eval set never happened to trigger it, which is itself worth knowing rather than assuming it works.

---

## Note: MLflow tracking

This eval run is also logged to `evals/mlflow.db` (SQLite backend — no server needed), one MLflow run
per test case, tagged with the model (`openai/gpt-oss-20b`) and test-case id, with real metrics:
`price_movement_pct`, `comps_count`, `rounds_run`, `outcome_deal_closed`, `errored`, `duration_sec`.
View it locally with:

```bash
cd evals && mlflow ui --backend-store-uri sqlite:///mlflow.db
```

This is the same backend the dashboard's version-comparison page will read from — re-running
`run_eval.py` after a prompt change (e.g. v1.1 above) adds new runs without losing v1.0's numbers, so
scores are comparable across versions rather than overwritten.
