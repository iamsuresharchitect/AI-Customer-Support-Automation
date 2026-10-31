"""Customer Query Agent: classifies the complaint."""

from autogen_agentchat.agents import AssistantAgent

CATEGORIES = ["Shipping", "Refund", "Account", "Product", "Billing", "Other"]
URGENCIES = ["Low", "Medium", "High"]
SENTIMENTS = ["Positive", "Neutral", "Frustrated", "Angry", "Very Angry"]

SYSTEM_MESSAGE = f"""You are the Customer Query Agent for ShopNest, an online store in India.
Your only job is to understand the customer's complaint. Do not answer the customer or suggest solutions.

Reply with exactly these four lines and nothing else:
CATEGORY: one of {", ".join(CATEGORIES)}
URGENCY: one of {", ".join(URGENCIES)}
SENTIMENT: one of {", ".join(SENTIMENTS)}
SUMMARY: one sentence describing the problem and what the customer wants

Guidance:
- Billing is for charges and payments; Refund is for returns and money back on an order; Product is for faulty, broken or wrong items and product questions.
- URGENCY High: money taken wrongly, legal threats, fraud or security issues, or a customer demanding immediate action. Medium: an order or account problem that blocks the customer. Low: general questions.
- SENTIMENT Frustrated: annoyed but polite. Angry: hostile tone, demands, threats or shouting (capitals, many exclamation marks). Very Angry: abusive or threatening legal action."""


def create_query_agent(model_client) -> AssistantAgent:
    return AssistantAgent(
        name="query_agent",
        description="Understands the complaint: category, urgency, sentiment and a one-line summary.",
        model_client=model_client,
        system_message=SYSTEM_MESSAGE,
    )
