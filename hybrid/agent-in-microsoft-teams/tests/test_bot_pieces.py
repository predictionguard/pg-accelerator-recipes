"""Tests for the pieces that are easy to get subtly wrong."""

from __future__ import annotations

import pytest
from botbuilder.core import TurnContext
from botbuilder.schema import (
    Activity,
    ActivityTypes,
    ChannelAccount,
    ConversationAccount,
    Entity,
)

from agentforge_teams.bot import ForgeTeamsBot
from agentforge_teams.conversation import InMemoryHistoryStore
from agentforge_teams.forge_client import ForgeAgent, ForgeError


# --------------------------------------------------------------- response parsing

def test_extract_text_from_openai_shaped_response():
    response = {
        "choices": [{"message": {"role": "assistant", "content": " hello there "}}]
    }
    assert ForgeAgent._extract_text(response) == "hello there"


def test_extract_text_rejects_empty_content():
    response = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    with pytest.raises(ForgeError, match="finish_reason=length"):
        ForgeAgent._extract_text(response)


def test_extract_text_rejects_no_choices():
    with pytest.raises(ForgeError, match="no choices"):
        ForgeAgent._extract_text({"choices": []})


# --------------------------------------------------- deployment URL handling
# AGENT_FORGE_BASE_URL varies per customer (public gateway, dedicated, self-hosted),
# so it gets validated rather than assumed.

def _settings(monkeypatch, url=None):
    from agentforge_teams.config import Settings

    monkeypatch.setenv("AGENT_API_KEY", "k" * 20)
    monkeypatch.setenv("AGENT_ID", "agent-1")
    if url is None:
        monkeypatch.delenv("AGENT_FORGE_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("AGENT_FORGE_BASE_URL", url)
    return Settings()


def test_base_url_defaults_to_the_public_gateway(monkeypatch):
    from agentforge_teams.config import DEFAULT_FORGE_BASE_URL

    assert _settings(monkeypatch).forge_base_url == DEFAULT_FORGE_BASE_URL


def test_api_url_appends_the_version_segment(monkeypatch):
    """The env var is the host; the code owns `/v1`."""
    settings = _settings(monkeypatch, "https://forge.acme-corp.com")
    settings.validate_forge()
    assert settings.forge_api_url == "https://forge.acme-corp.com/v1"


def test_base_url_accepts_self_hosted_http_with_a_port(monkeypatch):
    settings = _settings(monkeypatch, "http://10.0.0.5:8080")
    settings.validate_forge()
    assert settings.forge_api_url == "http://10.0.0.5:8080/v1"


def test_base_url_trailing_slash_is_stripped(monkeypatch):
    """Otherwise the join yields `//v1/chat/completions`."""
    assert _settings(monkeypatch, "https://f.acme.com/").forge_api_url == (
        "https://f.acme.com/v1"
    )


def test_base_url_with_version_segment_is_trimmed(monkeypatch, caplog):
    """Pasting `https://host/v1` must not produce `/v1/v1/chat/completions`."""
    with caplog.at_level("WARNING"):
        settings = _settings(monkeypatch, "https://f.acme.com/v1")
    assert settings.forge_api_url == "https://f.acme.com/v1"
    assert "without a version segment" in caplog.text


def test_base_url_without_a_scheme_is_rejected(monkeypatch):
    from agentforge_teams.config import ConfigError

    with pytest.raises(ConfigError, match="must start with https://"):
        _settings(monkeypatch, "forge.acme.com").validate_forge()


# ------------------------------------------------------- typed response handling

def test_extract_text_from_typed_chat_completion():
    """The real return type: a pydantic ChatCompletion, not a dict."""
    from openai.types.chat import ChatCompletion

    completion = ChatCompletion.model_validate(
        {
            "id": "c1",
            "created": 0,
            "model": "agent",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": " hi from the agent "},
                }
            ],
        }
    )
    assert ForgeAgent._extract_text(completion) == "hi from the agent"


def test_empty_content_error_includes_the_raw_payload():
    """Without the body there is nothing to debug an odd agent shape from."""
    response = {"choices": [{"message": {"content": ""}, "finish_reason": "tool_calls"}]}
    with pytest.raises(ForgeError) as err:
        ForgeAgent._extract_text(response)
    assert "tool_calls" in str(err.value)
    assert "choices" in str(err.value)


def test_status_errors_get_an_actionable_hint():
    # openai 3.x is built on httpx2, not httpx.
    import httpx2
    from openai import AuthenticationError

    from agentforge_teams.forge_client import _describe_status_error

    exc = AuthenticationError(
        message="Invalid API key",
        response=httpx2.Response(
            401, request=httpx2.Request("POST", "https://forge-api.example/v1")
        ),
        body=None,
    )
    assert "AGENT_API_KEY is invalid" in _describe_status_error(exc)


# ------------------------------------------------------------------ mention strip

def test_remove_recipient_mention_strips_teams_markup():
    """In a channel, Teams prepends `<at>Bot</at>` to the user's text."""
    activity = Activity(
        type=ActivityTypes.message,
        text="<at>Agent Forge</at> what is our churn rate?",
        recipient=ChannelAccount(id="28:bot-id", name="Agent Forge"),
        entities=[
            Entity().deserialize(
                {
                    "type": "mention",
                    "text": "<at>Agent Forge</at>",
                    "mentioned": {"id": "28:bot-id", "name": "Agent Forge"},
                }
            )
        ],
    )
    assert TurnContext.remove_recipient_mention(activity).strip() == (
        "what is our churn rate?"
    )


def _group_message(entities: list | None) -> Activity:
    return Activity(
        type=ActivityTypes.message,
        text="hi",
        recipient=ChannelAccount(id="28:bot-id", name="Agent Forge"),
        conversation=ConversationAccount(id="19:channel-thread", is_group=True),
        entities=entities,
    )


def _mention(bot_id: str) -> Entity:
    return Entity().deserialize(
        {
            "type": "mention",
            "text": "<at>Agent Forge</at>",
            "mentioned": {"id": bot_id, "name": "Agent Forge"},
        }
    )


def test_addressed_to_bot_requires_a_mention_of_this_bot():
    """A channel message only belongs to the bot if it names *this* bot.

    `get_mentions` hands back raw `Entity` objects, so the mentioned id sits in
    `additional_properties` — a bot with no entities, or one mentioning someone
    else, is somebody else's conversation.
    """
    addressed = ForgeTeamsBot._addressed_to_bot

    assert addressed(_group_message([_mention("28:bot-id")])) is True
    assert addressed(_group_message([_mention("29:a-colleague")])) is False
    assert addressed(_group_message(None)) is False
    assert addressed(_group_message([])) is False


# ----------------------------------------------------------------- history window

async def test_history_is_bounded_to_max_messages():
    store = InMemoryHistoryStore()
    for i in range(10):
        await store.append(
            "conv-1",
            {"role": "user", "content": f"q{i}"},
            {"role": "assistant", "content": f"a{i}"},
            max_messages=4,
        )
    history = await store.get("conv-1")
    assert [m["content"] for m in history] == ["q8", "a8", "q9", "a9"]


async def test_history_is_isolated_per_conversation():
    store = InMemoryHistoryStore()
    await store.append("a", {"role": "user", "content": "x"}, max_messages=10)
    await store.append("b", {"role": "user", "content": "y"}, max_messages=10)
    assert await store.get("a") == [{"role": "user", "content": "x"}]
    assert await store.get("b") == [{"role": "user", "content": "y"}]


async def test_history_clear():
    store = InMemoryHistoryStore()
    await store.append("a", {"role": "user", "content": "x"}, max_messages=10)
    await store.clear("a")
    assert await store.get("a") == []


async def test_history_expires_after_ttl():
    store = InMemoryHistoryStore(ttl_seconds=0)
    await store.append("a", {"role": "user", "content": "x"}, max_messages=10)
    assert await store.get("a") == []
