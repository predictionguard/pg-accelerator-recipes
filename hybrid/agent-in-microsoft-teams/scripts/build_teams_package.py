"""Build the sideloadable Teams app package for one agent.

Fills the `${{PLACEHOLDER}}` fields in `appPackage/manifest.json` from your
environment and zips manifest + icons into `appPackage/<app>.zip`.

    uv run python scripts/build_teams_package.py

Every agent you expose needs its own `TEAMS_APP_ID` — Teams uses it as the app's
identity, so two packages sharing one id are treated as the same app and the
second install overwrites the first. If `TEAMS_APP_ID` isn't set, one is
generated and printed for you to paste into `.env`; keep it stable afterwards, or
Teams will treat your next upload as a brand new app instead of an update.
"""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
import zipfile
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "appPackage"

PLACEHOLDER = re.compile(r"\$\{\{(\w+)\}\}")


def load_env() -> dict[str, str]:
    """`.env` first, then `local.settings.json`, then the real environment."""
    values: dict[str, str] = {
        k: v for k, v in dotenv_values(ROOT / ".env").items() if v
    }

    local = ROOT / "local.settings.json"
    if local.exists():
        try:
            for k, v in json.loads(local.read_text()).get("Values", {}).items():
                values.setdefault(k, v)
        except json.JSONDecodeError:
            print("! local.settings.json isn't valid JSON — ignoring it")

    for key in ("MicrosoftAppId", "TEAMS_APP_ID", "TEAMS_APP_NAME", "AGENT_NAME"):
        if os.environ.get(key):
            values[key] = os.environ[key]

    return {k: v for k, v in values.items() if not str(v).startswith("<")}


def resolve_fields(env: dict[str, str]) -> tuple[dict[str, str], bool]:
    bot_id = (sys.argv[1] if len(sys.argv) > 1 else env.get("MicrosoftAppId", "")).strip()
    if not bot_id:
        sys.exit(
            "No bot id. Pass it as an argument, or set MicrosoftAppId in .env.\n"
            "It is the Azure Bot's Entra app id — deploy_azure.sh writes it for you."
        )

    name = env.get("TEAMS_APP_NAME", "Agent Forge").strip()
    teams_app_id = env.get("TEAMS_APP_ID", "").strip()
    generated = not teams_app_id
    if generated:
        teams_app_id = str(uuid.uuid4())

    return {
        "TEAMS_APP_ID": teams_app_id,
        "BOT_ID": bot_id,
        "APP_NAME_SHORT": name[:30],  # Teams hard-limits this to 30 characters
        "APP_NAME_FULL": env.get("TEAMS_APP_NAME_FULL", name)[:100],
        "APP_DESCRIPTION_SHORT": env.get(
            "TEAMS_APP_DESCRIPTION",
            f"Chat with the {name} agent, powered by Prediction Guard Agent Forge.",
        )[:80],
        "APP_DESCRIPTION_FULL": env.get(
            "TEAMS_APP_DESCRIPTION_FULL",
            f"Connects Microsoft Teams to {name}, an agent hosted on Prediction Guard "
            "Agent Forge. Message it directly, add it to a group chat, or @mention it "
            "in a channel. Type /reset to clear the conversation history.",
        )[:4000],
        "DEVELOPER_NAME": env.get("DEVELOPER_NAME", "Prediction Guard"),
        "DEVELOPER_URL": env.get("DEVELOPER_URL", "https://predictionguard.com"),
    }, generated


def main() -> None:
    env = load_env()
    fields, generated = resolve_fields(env)

    template = (PKG / "manifest.json").read_text()

    unknown = {m for m in PLACEHOLDER.findall(template)} - fields.keys()
    if unknown:
        sys.exit(f"manifest.json has placeholders I can't fill: {sorted(unknown)}")

    manifest = json.loads(PLACEHOLDER.sub(lambda m: fields[m.group(1)], template))

    missing_icons = [n for n in ("color.png", "outline.png") if not (PKG / n).exists()]
    if missing_icons:
        sys.exit(f"Missing icon(s): {', '.join(missing_icons)}")

    slug = re.sub(r"[^a-z0-9]+", "-", fields["APP_NAME_SHORT"].lower()).strip("-")
    out = PKG / f"{slug or 'agentforge'}-teams.zip"

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        zf.write(PKG / "color.png", "color.png")
        zf.write(PKG / "outline.png", "outline.png")

    print(f"✓ {out.relative_to(ROOT)}")
    print(f"    app name    : {fields['APP_NAME_SHORT']}")
    print(f"    Teams app id: {fields['TEAMS_APP_ID']}")
    print(f"    bot id      : {fields['BOT_ID']}")

    if generated:
        print(
            "\n! Generated a new Teams app id. Add this to .env so future builds\n"
            "  update the same Teams app instead of creating a duplicate:\n"
            f"    TEAMS_APP_ID={fields['TEAMS_APP_ID']}"
        )

    print("\nUpload in Teams: Apps → Manage your apps → Upload a custom app")


if __name__ == "__main__":
    main()
