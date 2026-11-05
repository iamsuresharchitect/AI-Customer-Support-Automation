"""Follow-up handling: rewrite a customer's reply on an earlier ticket into one standalone request.

Every follow-up is rewritten by the LLM, whatever its length, so that retrieval and the agents see
the full context ("it still hasn't come" becomes "Order ORD-4512 (headphones) has still not
arrived after the courier trace was promised...").
"""

from autogen_core.models import SystemMessage, UserMessage

from agents.model_client import get_model_client

REWRITE_PROMPT = """You rewrite customer follow-up messages for a support team.
You get an earlier support ticket (the customer's complaint and our reply) and the customer's new follow-up message.
Write ONE standalone support request that someone who has not seen the earlier ticket can act on:
- Keep every concrete detail: order ID, product, amounts, dates, what was already promised or tried.
- State what the customer wants now.
- Write it in the same language as the follow-up message, in the first person, as the customer.
- Reply with the rewritten request only, no preamble."""


async def rewrite_followup(original_complaint: str, previous_reply: str, followup: str, model_client=None) -> str:
    """Return the follow-up as a standalone request; falls back to joining the texts if the LLM call fails."""
    context = (
        f"Earlier complaint:\n{original_complaint.strip()}\n\n"
        f"Our earlier reply:\n{previous_reply.strip() or '(no reply sent yet)'}\n\n"
        f"New follow-up message:\n{followup.strip()}"
    )
    try:
        client = model_client or get_model_client()
        result = await client.create([SystemMessage(content=REWRITE_PROMPT), UserMessage(content=context, source="user")])
        text = result.content.strip() if isinstance(result.content, str) else ""
        if text:
            return text
    except Exception:
        pass
    return f"{followup.strip()} (Follow-up to my earlier request: {original_complaint.strip()})"
