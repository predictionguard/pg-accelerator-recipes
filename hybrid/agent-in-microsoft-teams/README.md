# Agent Forge → Microsoft Teams

A working reference for putting a **Prediction Guard Agent Forge** agent into
**Microsoft Teams**, using nothing but the agent's API capability.

Every Agent Forge agent exposes a standard chat completions endpoint:

```bash
curl -X POST "$AGENT_FORGE_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $AGENT_API_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"model": "<your-agent-id>", "messages": [{"role": "user", "content": "Hello!"}]}'
```

where `AGENT_FORGE_BASE_URL` is your deployment's host — `https://forge-api.predictionguard.com`
for the public gateway, and something else for dedicated or self-hosted
deployments.

That single endpoint is enough to reach any platform your organisation already
uses. This repo does it for Teams: build and refine your agent in Agent Studio,
then run these steps to have colleagues talk to it from the Teams client they
already have open — no separate app for them to learn, no chat UI to build.

If your org runs on Teams, this is the shortest path from "the agent works in
Agent Studio" to "the team is using it".

## What your colleagues get

- **Direct messages** — a 1:1 chat with the agent.
- **Channels** — `@mention` the agent and it answers **inside that thread**. Each
  thread keeps its own separate context.
- **Group chats** — add it to any group conversation.
- **Follow-up questions** — it remembers the recent conversation, so "summarise
  that one" works.
- **`/reset`** — clears the history for that conversation.
- **A typing indicator** while the agent works, so a slow answer doesn't look
  like a hang.

## How it fits together

```
Teams client
   │  activity (message / @mention)
   ▼
Azure Bot Service ──► POST /api/messages   (this repo, on Azure Functions)
                          │
                          ├─ validate the request came from Teams
                          ├─ strip the @mention, load recent history
                          ├─ POST /v1/chat/completions ──► your Agent Forge agent
                          └─ post the answer back into the conversation
```

Three moving parts, and you create all three below:

| Part | What it is |
| --- | --- |
| **Function App** | Runs this code. Holds your agent id + API key. |
| **Azure Bot** | Teams' entry point. Points at the Function App's URL. |
| **Teams app package** | The zip colleagues install. Points at the Azure Bot. |

---

# Getting started

## Prerequisites

| | |
| --- | --- |
| An Agent Forge agent | Its **agent id**, a scoped **Agent Studio API key**, and your deployment's **host** |
| An Azure subscription | Permission to create resources (Contributor on a resource group) |
| Microsoft Teams | Your tenant must allow custom app upload — see [Permissions](#permissions-and-who-has-to-approve-what) |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Azure CLI | `brew install azure-cli`, then `az login` |
| Functions Core Tools | `brew tap azure/functions && brew install azure-functions-core-tools@4` |

## 1. Clone and configure

```bash
git clone <this-repo> agentforge-teams
cd agentforge-teams
uv sync --all-groups

cp .env.example .env
```

Fill in the two required values in `.env`:

```ini
AGENT_API_KEY=sk-agentstudio-...   # a scoped key bound to this agent
AGENT_ID=your-agent-id             # what gets sent as "model"
```

Both come from Agent Studio — the key from **Settings → API Keys**, the agent id
from the agent's **API** tab.

**If you're not on the public gateway, set your host too:**

```ini
AGENT_FORGE_BASE_URL=https://agents.your-org.com
```

Agent Forge is deployed per customer, so this varies — dedicated, regional, and
self-hosted deployments all differ. Use the host shown in Agent Studio, **without**
a version segment; the code appends `/v1` itself. It defaults to the public
gateway, and is validated at startup so a mistyped value fails immediately rather
than on the first message someone sends.

Leave everything else alone for now; the deploy script fills in the Azure values.

## 2. Check the agent is reachable

```bash
uv run python scripts/smoke_forge.py
```

This calls your agent directly — no Teams, no Azure — and drops you into a chat
prompt. **Do this before anything else**: it isolates "is my key and agent id
right?" from every later question, and its errors name the specific cause.

## 3. Try the bot locally

No Azure and no Teams needed yet. Two terminals:

```bash
# terminal A — the bot
uv run uvicorn agentforge_teams.app:app --reload --port 3978
```

```bash
# terminal B — a stand-in for Teams
uv run python scripts/local_teams_sim.py
```

[local_teams_sim.py](scripts/local_teams_sim.py) impersonates both halves of
Teams — it sends activities to the bot and receives its replies — so the whole
turn runs exactly as it will in production. Worth testing:

1. Ask a question.
2. Ask a **follow-up that depends on the answer** ("summarise that in one
   sentence"). This is the check that matters; without history the bot feels
   broken in Teams.
3. `/reset`, then ask the follow-up again — it should have lost the thread.
4. Quit and re-run with `--channel` to simulate an `@mention` in a channel.

## 4. Deploy to Azure Functions

```bash
export APP_NAME=my-agent-teams        # names every Azure resource; must be globally unique
./scripts/deploy_azure.sh
```

The script reads your `.env` and is safe to re-run — use it to redeploy after
changing anything. It will:

1. Create a resource group, storage account, and Function App (Flex Consumption,
   Python 3.12).
2. Register an Entra application for the bot and generate a client secret.
3. Apply your agent id, key, and behaviour settings as Application Settings.
4. Deploy the code.
5. Create the Azure Bot resource pointing at
   `https://<app>.azurewebsites.net/api/messages` and enable the Teams channel.
6. Build the Teams app package.

Confirm it's healthy:

```bash
curl https://<your-app>.azurewebsites.net/api/healthz
```

`"status": "ok"` means the agent id and key arrived intact.

## 5. Install it in Teams

The deploy script leaves a zip in `appPackage/`. In Teams:

**Apps → Manage your apps → Upload a custom app → Upload for me or my teams**

Then pick the zip. Message the bot directly, or add it to a channel and
`@mention` it.

To share it with the whole organisation instead, hand the zip to a Teams
Administrator — see [Permissions](#permissions-and-who-has-to-approve-what).

---

# Exposing more than one agent

Each agent needs its own bot identity and its own Teams app, because Teams routes
by bot id and identifies apps by their manifest id. The practical approach is one
deployment per agent.

**Per agent — must differ:**

| Setting | Why |
| --- | --- |
| `APP_NAME` | Names the Azure resources; must be globally unique |
| `AGENT_ID` | Which agent this deployment talks to |
| `TEAMS_APP_NAME` | How colleagues tell them apart in the app list |
| `TEAMS_APP_ID` | Teams' identity for the app — a **new GUID per agent** |

**Can be shared:** your `AGENT_API_KEY`, `AGENT_FORGE_BASE_URL` (agents on the
same deployment), the Azure subscription, and the resource group (pass
`RESOURCE_GROUP=shared-rg` to keep them together).

The cleanest way to manage several is one env file each:

```bash
cp .env research-agent.env      # edit: agent id, TEAMS_APP_NAME, TEAMS_APP_ID (blank)
cp .env support-agent.env       # edit: same, different values

# deploy one
cp research-agent.env .env
APP_NAME=research-agent-teams ./scripts/deploy_azure.sh
```

> **`TEAMS_APP_ID` matters more than it looks.** Leave it blank the first time and
> the build script generates one and prints it — **paste that back into that
> agent's env file**. If it changes, Teams treats your next upload as a brand new
> app rather than an update. If two agents share one, installing the second
> overwrites the first.

---

# Customising an agent's presence

All of these are Application Settings on the Function App (`.env` locally), so
changing them needs no code edit. After changing them in Azure, run
`./scripts/deploy_azure.sh` again, or set them in the portal under
**Configuration → Application settings**.

### The welcome message

Sent when someone installs the bot or adds it to a channel:

```ini
WELCOME_MESSAGE=Hi! I'm the research assistant. Ask me about recent AI papers, or type /reset to start over.
```

Leave it blank for the built-in default. Worth setting — it's the first thing
anyone sees, and it's where you tell people what the agent is actually for.

### Framing the agent's replies

```ini
SYSTEM_PROMPT=Answer concisely for a Teams chat. Prefer short paragraphs over long lists.
```

Prepended to every request. Your agent's own instructions in Agent Studio still
apply; this adds Teams-specific framing on top — useful because what reads well
in a web playground is often too long for a chat window.

### How much it remembers

```ini
HISTORY_TURNS=8            # user+assistant pairs replayed to the agent
HISTORY_TTL_SECONDS=3600   # forget a conversation after this long idle
```

Higher `HISTORY_TURNS` means better follow-up handling and more tokens per turn.

### Name, description, and icons

`TEAMS_APP_NAME` (max 30 characters) drives the name and the default
descriptions. For finer control set `TEAMS_APP_DESCRIPTION`, `DEVELOPER_NAME`, and
`DEVELOPER_URL`.

For the icons, replace these two files and rebuild — the sizes are enforced by
Teams:

| File | Size | Notes |
| --- | --- | --- |
| `appPackage/color.png` | 192×192 | Full colour |
| `appPackage/outline.png` | 32×32 | Transparent background, single-colour shape |

Then rebuild the package and re-upload it in Teams:

```bash
uv run python scripts/build_teams_package.py
```

Anything in [appPackage/manifest.json](appPackage/manifest.json) not exposed as a
setting — extra bot scopes, additional commands — can be edited directly. The
`${{PLACEHOLDER}}` fields are filled from your env at build time.

---

# Permissions and who has to approve what

Most of this you can do yourself. Two steps may need an administrator, and it's
worth checking before you start.

| Step | Requires | If you don't have it |
| --- | --- | --- |
| Create Azure resources | **Contributor** on a subscription or resource group | Ask for a resource group you own |
| Register the bot's Entra app | Tenant setting *Users can register applications* = **Yes**, or the **Application Developer** role | An admin creates the app registration; then pass its id — see below |
| Enable the Azure Bot resource | `Microsoft.BotService` provider registered on the subscription | `az provider register --namespace Microsoft.BotService` |
| **Upload a custom app** in Teams | Teams app setup policy allowing **Upload custom apps** | A **Teams Administrator** must enable it, or publish on your behalf |
| Publish org-wide | **Teams Administrator** | Hand them the zip from `appPackage/` |

**Checking the Teams side first:** if **Apps → Manage your apps** has no *Upload
a custom app* option, custom app upload is disabled for your tenant. An admin
turns it on in Teams admin center → **Teams apps → Setup policies → Upload custom
apps**. There is no way around this from the repo.

**If you can't register the Entra app yourself,** have an admin create a
multi-tenant app registration with a client secret, then set `MicrosoftAppId` and
`MicrosoftAppPassword` in `.env` and comment out the `az ad app` steps in
[deploy_azure.sh](scripts/deploy_azure.sh).

The bot needs **no Microsoft Graph permissions** and requests no access to your
mailbox, files, or calendar. It only sees messages that are sent directly to it
or that `@mention` it.

---

# Configuration reference

| Variable | Required | Default | |
| --- | :---: | --- | --- |
| `AGENT_API_KEY` | ✅ | — | Scoped Agent Studio key (`sk-agentstudio-…`) |
| `AGENT_ID` | ✅ | — | Your agent's id |
| `AGENT_FORGE_BASE_URL` | | public gateway | Your deployment's host, no `/v1` |
| `AGENT_FORGE_TIMEOUT` | | `120` | Seconds before giving up |
| `MicrosoftAppId` / `MicrosoftAppPassword` | for Teams | — | Written by the deploy script. Blank ⇒ local only |
| `MicrosoftAppType` | | `MultiTenant` | Or `SingleTenant` |
| `MicrosoftAppTenantId` | if single-tenant | — | |
| `WELCOME_MESSAGE` | | built-in | Shown on install |
| `SYSTEM_PROMPT` | | — | Prepended to every request |
| `HISTORY_TURNS` | | `8` | Turns replayed |
| `HISTORY_TTL_SECONDS` | | `3600` | Idle expiry |
| `TEAMS_APP_NAME` | | `Agent Forge` | Max 30 characters |
| `TEAMS_APP_ID` | per agent | generated | Unique GUID per agent; keep it stable |

---

# Troubleshooting

**`Invalid API key` although `.env` looks right.** An exported shell variable
beats `.env` — the app logs a warning naming any variable it ignored for this
reason. Fix with `unset AGENT_API_KEY`. This usually happens after running
a command with an inline `AGENT_API_KEY=... uv run ...`.

**Editing `.env` changes nothing.** Config is read once at startup, and
`--reload` only watches `.py` files. Restart the bot.

**The local simulator says the key doesn't match.** A bot from an earlier run is
holding the port with different settings. Find and stop it:

```bash
lsof -nP -iTCP:3978 -sTCP:LISTEN
```

**The bot never replies in Teams.** Check `/api/healthz` first. If it reports
`ok`, tail the logs while sending a message:

```bash
az webapp log tail --name <app>-func --resource-group <app>-rg
```

**`no agent with id ... was found`.** `AGENT_ID` is wrong, that key
can't see that agent, or `AGENT_FORGE_BASE_URL` points at a different deployment than
the one the agent lives on. `/healthz` echoes both values — check them there
first.

**`Couldn't reach <url>` or every request 404s.** `AGENT_FORGE_BASE_URL` is wrong.
It must be the host on its own (`https://host`) — not `https://host/v1` and not
the full `/chat/completions` path, since the code appends the rest. A pasted
`/v1` is trimmed with a warning rather than producing `/v1/v1`.

**The agent replies but ignores context.** Conversation history lives in process
memory, so it resets when the app restarts and is not shared between instances.
The deploy script pins the app to one instance for this reason. To raise that,
implement the `HistoryStore` protocol in
[conversation.py](agentforge_teams/conversation.py) against Azure Table Storage
or Redis first.

---

# What's in here

| Path | |
| --- | --- |
| [function_app.py](function_app.py) | Azure Functions entry point |
| [agentforge_teams/app.py](agentforge_teams/app.py) | `POST /api/messages`, `GET /healthz` |
| [agentforge_teams/bot.py](agentforge_teams/bot.py) | Mentions, history, typing, `/reset` |
| [agentforge_teams/forge_client.py](agentforge_teams/forge_client.py) | Calls the agent's chat endpoint |
| [agentforge_teams/conversation.py](agentforge_teams/conversation.py) | Per-conversation history |
| [agentforge_teams/config.py](agentforge_teams/config.py) | Settings |
| [appPackage/](appPackage/) | Teams manifest and icons |
| [scripts/deploy_azure.sh](scripts/deploy_azure.sh) | Provision and deploy |
| [scripts/smoke_forge.py](scripts/smoke_forge.py) | Test the agent alone |
| [scripts/local_teams_sim.py](scripts/local_teams_sim.py) | Test the bot without Teams |
| [scripts/build_teams_package.py](scripts/build_teams_package.py) | Build the upload zip |

Dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`). Azure Functions
builds with pip, so `requirements.txt` is generated — the deploy script refreshes
it automatically. Regenerate manually with:

```bash
uv export --no-dev --no-hashes --no-emit-project --format requirements-txt -o requirements.txt
```

```bash
uv run pytest -q      # tests
```

# Known limits

- **History is per-instance and in memory** — it doesn't survive a restart. Fine
  for a demo; see [conversation.py](agentforge_teams/conversation.py) for the
  seam to make it durable.
- **Group chats share one history.** Everyone in the chat contributes to the same
  context. For per-person isolation, key history on the sender id as well.
- **Replies are plain markdown**, not Adaptive Cards. Bold, italics, links, and
  bullet lists render in Teams; tables and nested lists don't render reliably.
- **Answers arrive complete**, not streamed token by token.
- **In a channel, the bot only sees messages addressed to it** — not the
  surrounding discussion. Reading full channel history needs additional Teams
  permissions and Graph calls.
