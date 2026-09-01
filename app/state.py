"""
Negotiation session state — the agent's working memory for ONE listing/seller
negotiation (see DESIGN_DOC.md Section 4c: in-context/session state only, no
external DB in v1).
"""
from dataclasses import dataclass, field
from typing import Literal, Optional


Phase = Literal["research", "strategy", "negotiate", "done"]


@dataclass
class TranscriptTurn:
    role: str  # "agent_message" | "seller_reply" | "system_note"
    text: str


@dataclass
class NegotiationState:
    # Phase 1: listing + research
    listing_text: str = ""
    asking_price: Optional[float] = None
    fair_price_low: Optional[float] = None
    fair_price_high: Optional[float] = None
    research_confidence_note: str = ""
    comps_summary: str = ""

    # Phase 2: buyer constraints + strategy
    budget: Optional[float] = None
    urgency: str = ""
    dealbreakers: str = ""
    opening_offer: Optional[float] = None
    walkaway_price: Optional[float] = None
    ladder_note: str = ""  # plain-language concession ladder description
    strategy_confirmed: bool = False

    # Phase 3: negotiation loop
    round_number: int = 0
    transcript: list = field(default_factory=list)  # list[TranscriptTurn]
    last_agent_message: str = ""

    # Phase 4: outcome
    outcome: Optional[str] = None  # "deal_closed" | "walked_away"
    final_price: Optional[float] = None
    savings_vs_ask: Optional[float] = None
    stop_reason: str = ""
    next_action: str = ""

    phase: Phase = "research"

    def add_turn(self, role: str, text: str) -> None:
        self.transcript.append(TranscriptTurn(role=role, text=text))
