"""Runs the assignment's test complaints (plus our own) through the team and prints a summary.
Escalated tickets stay "Pending approval" so they can be reviewed later in the app's Approvals tab.

    python test_cases.py          # all cases
    python test_cases.py 5        # only case 5
"""

import asyncio
import sys

from team import TicketOutcome, build_team, run_ticket

# (complaint, customer_name, order_id, expected status)
TEST_CASES = [
    ("Where is my order? It was supposed to arrive yesterday.", "Priya", "ORD-4512", "Resolved"),
    ("I want to return the shoes I bought last week. How do I get a refund?", "Arjun", "ORD-4630", "Resolved"),
    ("I forgot my password and can't log in.", "Meena", "", "Resolved"),
    ("The blender I received is broken. Can I get a replacement?", "Karthik", "ORD-4701", "Resolved"),
    ("You charged my card three times! Fix this now or I'm contacting my bank and a lawyer.", "Rahul", "ORD-4719", "Escalated"),
    ("Do you sell gift cards for a company of 500 employees with custom branding?", "Anita", "", "Escalated"),
    # Our own cases
    ("Can I change the delivery address? I just placed the order an hour ago.", "Deepa", "ORD-4802", "Resolved"),
    ("Someone logged into my account and placed orders I never made. This is fraud!", "Vikram", "", "Escalated"),
    # Hindi: "My order hasn't arrived yet. It was supposed to come yesterday." The reply should be in Hindi.
    ("मेरा ऑर्डर अभी तक नहीं आया। यह कल आना था।", "Priya", "ORD-4512", "Resolved"),
    # Tamil: "I need to return the shoes I bought last week. How do I get my money back?"
    ("நான் கடந்த வாரம் வாங்கிய காலணிகளைத் திருப்பி அனுப்ப வேண்டும். பணத்தை எப்படித் திரும்பப் பெறுவது?", "Arjun", "ORD-4630", "Resolved"),
]


async def main(selected: list[int]) -> None:
    team = build_team()
    passed = 0
    for number, (complaint, name, order_id, expected) in enumerate(TEST_CASES, start=1):
        if selected and number not in selected:
            continue
        await team.reset()
        outcome = None
        async for item in run_ticket(complaint, name, order_id, team=team):
            if isinstance(item, TicketOutcome):
                outcome = item
        ok = outcome is not None and outcome.status == expected
        passed += ok
        print(f"\n#{number} {'PASS' if ok else 'FAIL'}  {complaint}")
        if outcome:
            print(f"   {outcome.category} | {outcome.urgency} | {outcome.sentiment} | {outcome.language} | sources: {outcome.used_sources} | confidence: {outcome.confidence}")
            print(f"   {outcome.ticket_id} {outcome.status} (expected {expected}) {outcome.escalation_reason}")
    total = len(selected) if selected else len(TEST_CASES)
    print(f"\n{passed}/{total} cases matched the expected status.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main([int(a) for a in sys.argv[1:]]))
