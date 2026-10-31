"""Shared Anthropic model client used by every agent."""

import os

from autogen_core.models import ModelInfo
from autogen_ext.models.anthropic import AnthropicChatCompletionClient
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-opus-5-5"


def _get_secret(name: str, default: str | None = None) -> str | None:
    """Read a setting from the environment (.env), falling back to Streamlit secrets when deployed."""
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st

        return st.secrets.get(name, default)
    except Exception:
        return default


def get_model_client() -> AnthropicChatCompletionClient:
    api_key = _get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing. Copy .env.example to .env and add your key.")

    model = _get_secret("ANTHROPIC_MODEL", DEFAULT_MODEL)
    client = AnthropicChatCompletionClient(
        model=model,
        api_key=api_key,
        max_tokens=8000,
        # AutoGen's built-in model list predates current Claude models, so describe the model ourselves.
        model_info=ModelInfo(
            vision=False,
            function_calling=True,
            json_output=False,
            structured_output=False,
            family="claude",
            multiple_system_messages=False,
        ),
    )

    # AutoGen always sends temperature=1.0, but current Claude models reject sampling parameters.
    # Strip them before each request reaches the Anthropic SDK.
    sdk_messages = client._client.messages
    original_create = sdk_messages.create

    async def create_without_sampling(**kwargs):
        for param in ("temperature", "top_p", "top_k"):
            kwargs.pop(param, None)
        return await original_create(**kwargs)

    sdk_messages.create = create_without_sampling
    return client
