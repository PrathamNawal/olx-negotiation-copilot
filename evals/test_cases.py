"""
Eval test case library — Phase 4 (eval-scorecard skill, Section 1).

Each test case supplies the agent's real input parameters end to end:
listing_text, budget, urgency, dealbreakers, and (for TC that reach the
negotiation phase) a scripted seller_reply used as a test fixture — the
same role a QA tester's "here's what the other side said" input plays.
This is NOT fabricated agent output; every research/strategy/negotiation/
final-outcome result in the eval run comes from a real Groq+Serper call.
"""

TEST_CASES = [
    {
        "id": "TC-01",
        "label": "Happy path",
        "listing_text": (
            "Apple iPhone 13 Pro Max Jade Green 256GB Box Kit\n"
            "₹ 44,444\n"
            "Apple iPhone 13 Pro Max, 256GB, Jade Green. Excellent condition, "
            "no scratches, battery health 91%. Full box with charger. "
            "Bengaluru, posted 8 days ago."
        ),
        "budget": 40000.0,
        "urgency": "Medium",
        "dealbreakers": "",
        "seller_reply": "I can do rs40000. My phone is in new condition",
    },
    {
        "id": "TC-02",
        "label": "Edge: minimal input",
        "listing_text": "Samsung phone, ₹8000, ok condition",
        "budget": 6500.0,
        "urgency": "Low",
        "dealbreakers": "",
        "seller_reply": "no less price, fix hai",
        "seller_reply_2": "chalo thik hai, 7000 me de dete hai",
    },
    {
        "id": "TC-03",
        "label": "Edge: maximal / complex input",
        "listing_text": (
            "Sony A7 III Mirrorless Camera Body + 28-70mm Kit Lens + 2 Batteries "
            "+ Extra 64GB SD Card + Original Sony Bag\n"
            "₹ 98,000 (slightly negotiable)\n"
            "Purchased Jan 2023, bill available, under warranty till Jan 2026. "
            "Shutter count ~9,400. No fungus, no dead pixels, sensor cleaned "
            "professionally last month. Selling due to upgrade to A7 IV. "
            "Pune, can courier pan-India at buyer's cost or meet locally. "
            "Serious buyers only, no time-wasters."
        ),
        "budget": 90000.0,
        "urgency": "High",
        "dealbreakers": "Must include original bill and warranty card; no COD, bank transfer only after physical inspection",
        "seller_reply": (
            "Thanks for the offer but 90k is too low for this kit, the lens alone "
            "is worth 30k new. Best I can do is 94000 if you pick up this week."
        ),
        "seller_reply_2": "Okay, meet me at 91000 final, aur kam nahi hoga.",
    },
    {
        "id": "TC-04",
        "label": "Niche / low-comp item",
        "listing_text": (
            "Yamaha RD350 1985 model, project bike, non-running\n"
            "₹ 1,85,000\n"
            "RD papers clear, single owner, engine needs rebuild, tank and "
            "side panels original paint, some rust on frame. Kolkata."
        ),
        "budget": 150000.0,
        "urgency": "Low",
        "dealbreakers": "Must have clear RC and no theft case",
        "seller_reply": "Bhai itna kam nahi hoga, ye rare bike hai. 1.75 tak soch sakta hoon, last price.",
    },
    {
        "id": "TC-05",
        "label": "Stress test: Hinglish, messy formatting, aggressive seller",
        "listing_text": (
            "OnePlus 11R 5G 🔥🔥 16gb/256gb urgent sale!!\n"
            "price 26k nego\n"
            "bilkul mint condition bro, 2 month old only, bill box sab hai, "
            "koi scratch nhi, cash preferred, Delhi NCR only pls"
        ),
        "budget": 20000.0,
        "urgency": "High",
        "dealbreakers": "Cash on delivery only, no advance payment",
        "seller_reply": "bhai 26 se ek rupya kam nahi hoga, chahiye to lo warna chhodo, bahut log line me hai",
    },
]
