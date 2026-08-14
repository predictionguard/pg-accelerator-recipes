"""Environment-driven configuration.

On Azure Functions these come from Application Settings; locally they come from
`local.settings.json` (loaded by the Functions host) or a `.env` file.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

logger = logging.getLogger(__name__)

# Absolute, so behaviour doesn't depend on the working directory you launched
# from. Missing file is a no-op, which is the normal case on Azure Functions
# where these arrive as Application Settings.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)


def _warn_if_env_shadows_dotenv() -> None:
    """Surface the trap where an exported variable silently wins over `.env`.

    `load_dotenv` deliberately does not override variables that are already
    exported, which is correct for production but makes for a baffling local
    failure: you edit `.env`, nothing changes, and the app keeps using a stale
    value from your shell. Values are never logged, only names.
    """
    if not _ENV_FILE.exists():
        return
    shadowed = [
        name
        for name, value in dotenv_values(_ENV_FILE).items()
        if value and name in os.environ and os.environ[name] != value
    ]
    if shadowed:
        logger.warning(
            "Ignoring .env for %s — already set in the environment, which takes "
            "precedence. Run `unset %s` if you meant to use the .env value.",
            ", ".join(shadowed),
            " ".join(shadowed),
        )


_warn_if_env_shadows_dotenv()


def _get(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


# Host only, no version segment — the API path is appended in code, matching the
# convention the other recipes in this repo use. Agent Forge is deployed per
# customer, so this default is only a starting point.
DEFAULT_FORGE_BASE_URL = "https://forge-api.predictionguard.com"

# A base URL that already carries the version segment, e.g. from someone pasting
# the URL out of a curl example.
_TRAILING_VERSION = re.compile(r"/v\d+$")


def _base_url() -> str:
    url = _get("AGENT_FORGE_BASE_URL", DEFAULT_FORGE_BASE_URL).rstrip("/")
    # Tolerate `https://host/v1`: the code appends `/v1` itself, so leaving it
    # would produce `/v1/v1/chat/completions` and a mystifying 404.
    if _TRAILING_VERSION.search(url):
        trimmed = _TRAILING_VERSION.sub("", url)
        logger.warning(
            "AGENT_FORGE_BASE_URL should be the host without a version segment — "
            "using %s instead of %s.",
            trimmed,
            url,
        )
        url = trimmed
    return url


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or unusable."""


@dataclass(frozen=True)
class Settings:
    # --- Agent Forge ---
    # Names match the conventions documented in the repository root README so
    # this recipe reads the same as its siblings.
    agent_api_key: str = field(default_factory=lambda: _get("AGENT_API_KEY"))
    agent_id: str = field(default_factory=lambda: _get("AGENT_ID"))
    forge_base_url: str = field(default_factory=_base_url)
    forge_timeout: float = field(
        default_factory=lambda: float(_get("AGENT_FORGE_TIMEOUT", "120"))
    )

    # --- Microsoft Bot Framework / Teams ---
    app_id: str = field(default_factory=lambda: _get("MicrosoftAppId"))
    app_password: str = field(default_factory=lambda: _get("MicrosoftAppPassword"))
    # "MultiTenant" (default) | "SingleTenant"
    app_type: str = field(
        default_factory=lambda: _get("MicrosoftAppType", "MultiTenant")
    )
    app_tenant_id: str = field(default_factory=lambda: _get("MicrosoftAppTenantId"))

    # --- Conversation behaviour ---
    # How many prior turns (user+assistant pairs) to replay to the agent.
    history_turns: int = field(default_factory=lambda: int(_get("HISTORY_TURNS", "8")))
    history_ttl_seconds: int = field(
        default_factory=lambda: int(_get("HISTORY_TTL_SECONDS", "3600"))
    )
    system_prompt: str = field(default_factory=lambda: _get("SYSTEM_PROMPT"))
    welcome_message: str = field(
        default_factory=lambda: _get(
            "WELCOME_MESSAGE",
            "Hi! I'm connected to an Agent Forge agent. Ask me anything, "
            "or type `/reset` to clear our conversation history.",
        )
    )

    @property
    def forge_api_url(self) -> str:
        """The versioned API root the chat endpoint hangs off."""
        return f"{self.forge_base_url}/v1"

    def validate_forge(self) -> None:
        """Fail fast on the settings without which nothing can work."""
        missing = [
            name
            for name, value in (
                ("AGENT_API_KEY", self.agent_api_key),
                ("AGENT_ID", self.agent_id),
            )
            if not value
        ]
        if missing:
            raise ConfigError(
                f"Missing required environment variable(s): {', '.join(missing)}"
            )

        # This varies per deployment, so a typo is likely; catching it here beats
        # a confusing HTTP failure on the first message someone sends.
        if not self.forge_base_url.startswith(("http://", "https://")):
            raise ConfigError(
                "AGENT_FORGE_BASE_URL must start with https:// — got "
                f"{self.forge_base_url!r}"
            )

    @property
    def key_fingerprint(self) -> str:
        """Short, non-reversible id for the key in use.

        Lets you tell at a glance whether a running bot holds the key you think
        it does — a stale process started with a different key is otherwise
        indistinguishable from a correctly configured one. Safe to expose: it is
        a truncated SHA-256, not the key.
        """
        if not self.agent_api_key:
            return "unset"
        return hashlib.sha256(self.agent_api_key.encode()).hexdigest()[:8]

    @property
    def is_single_tenant(self) -> bool:
        return self.app_type.casefold() == "singletenant"

    @property
    def auth_configured(self) -> bool:
        """Bot Framework auth is optional locally (Bot Framework Emulator)."""
        return bool(self.app_id and self.app_password)


settings = Settings()
