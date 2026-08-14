#!/usr/bin/env bash
#
# Provision + deploy the whole demo: Azure Function App, Entra app registration,
# Azure Bot resource, and the Teams channel.
#
# Prereqs:
#   - az CLI, logged in            (az login)
#   - Azure Functions Core Tools   (brew tap azure/functions && brew install azure-functions-core-tools@4)
#   - .env filled in (AGENT_API_KEY, AGENT_ID) — see .env.example
#
# Usage:
#   cp .env.example .env && $EDITOR .env
#   ./scripts/deploy_azure.sh
#
# Everything is name-derived from APP_NAME, so re-running with the same
# APP_NAME updates the existing deployment rather than creating a second one.

set -euo pipefail

cd "$(dirname "$0")/.."

# ------------------------------------------------------------------------- .env
# Loaded for anything not already exported, so an explicit
# `FOO=bar ./scripts/deploy_azure.sh` still wins — same precedence the app uses.
if [[ -f .env ]]; then
  while IFS='=' read -r key value; do
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key:-}" ]] || export "$key=$value"
  done < <(grep -v '^[[:space:]]*#' .env | grep '=')
fi

# ----------------------------------------------------------------- configuration
# APP_NAME names every Azure resource, so use a different one per agent.
APP_NAME="${APP_NAME:-agentforge-teams-demo}"
LOCATION="${LOCATION:-eastus}"
RESOURCE_GROUP="${RESOURCE_GROUP:-${APP_NAME}-rg}"
# Storage account names: 3-24 chars, lowercase alphanumeric only.
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-$(echo "st${APP_NAME}" | tr -cd '[:alnum:]' | tr '[:upper:]' '[:lower:]' | cut -c1-24)}"
FUNCTION_APP="${FUNCTION_APP:-${APP_NAME}-func}"
BOT_NAME="${BOT_NAME:-${APP_NAME}-bot}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"

AGENT_FORGE_BASE_URL="${AGENT_FORGE_BASE_URL:-https://forge-api.predictionguard.com}"

step() { printf '\n\033[1;36m▶ %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------------ sanity checks
command -v az >/dev/null || fail "az CLI not found."
command -v func >/dev/null || fail "Azure Functions Core Tools (func) not found."
az account show >/dev/null 2>&1 || fail "Not logged in. Run: az login"
[[ -n "${AGENT_API_KEY:-}" ]] || fail "AGENT_API_KEY is not set (put it in .env)."
[[ -n "${AGENT_ID:-}" ]] || fail "AGENT_ID is not set (put it in .env)."

step "Regenerating requirements.txt from uv.lock"
uv export --no-dev --no-hashes --no-emit-project --format requirements-txt -o requirements.txt

step "Resource group: $RESOURCE_GROUP ($LOCATION)"
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none

step "Storage account: $STORAGE_ACCOUNT"
az storage account create \
  --name "$STORAGE_ACCOUNT" \
  --resource-group "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --allow-blob-public-access false \
  --output none

step "Function app: $FUNCTION_APP (Flex Consumption, Python $PYTHON_VERSION)"
if ! az functionapp show --name "$FUNCTION_APP" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  # If Flex Consumption is unavailable in your region, swap the two flags below
  # for: --consumption-plan-location "$LOCATION" --os-type Linux --functions-version 4
  az functionapp create \
    --name "$FUNCTION_APP" \
    --resource-group "$RESOURCE_GROUP" \
    --storage-account "$STORAGE_ACCOUNT" \
    --flexconsumption-location "$LOCATION" \
    --runtime python \
    --runtime-version "$PYTHON_VERSION" \
    --output none
else
  echo "  already exists — reusing"
fi

# Conversation history lives in process memory, so a second instance would serve
# some turns with no context and look like the bot forgot the conversation.
# See README → "Things worth knowing" before raising this.
step "Pinning to a single instance (in-memory conversation history)"
az functionapp scale config set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --maximum-instance-count 1 \
  --output none || echo "  (skipped — not a Flex Consumption plan)"

# ------------------------------------------------------- Entra app + bot identity
step "Entra app registration for the bot"
APP_ID="$(az ad app list --display-name "$BOT_NAME" --query "[0].appId" -o tsv)"
if [[ -z "$APP_ID" ]]; then
  APP_ID="$(az ad app create \
    --display-name "$BOT_NAME" \
    --sign-in-audience AzureADandPersonalMicrosoftAccount \
    --query appId -o tsv)"
  echo "  created app id: $APP_ID"
else
  echo "  reusing app id: $APP_ID"
fi

step "Generating a fresh client secret"
APP_PASSWORD="$(az ad app credential reset \
  --id "$APP_ID" \
  --display-name "agentforge-teams" \
  --years 1 \
  --append \
  --query password -o tsv)"

step "Applying application settings"
az functionapp config appsettings set \
  --name "$FUNCTION_APP" \
  --resource-group "$RESOURCE_GROUP" \
  --settings \
    "AGENT_API_KEY=$AGENT_API_KEY" \
    "AGENT_ID=$AGENT_ID" \
    "AGENT_FORGE_BASE_URL=$AGENT_FORGE_BASE_URL" \
    "MicrosoftAppType=MultiTenant" \
    "MicrosoftAppId=$APP_ID" \
    "MicrosoftAppPassword=$APP_PASSWORD" \
    "HISTORY_TURNS=${HISTORY_TURNS:-8}" \
    "SYSTEM_PROMPT=${SYSTEM_PROMPT:-}" \
    "WELCOME_MESSAGE=${WELCOME_MESSAGE:-}" \
  --output none

step "Deploying code"
func azure functionapp publish "$FUNCTION_APP" --python

ENDPOINT="https://${FUNCTION_APP}.azurewebsites.net/api/messages"

step "Azure Bot resource: $BOT_NAME"
if ! az bot show --name "$BOT_NAME" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  az bot create \
    --name "$BOT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --app-type MultiTenant \
    --appid "$APP_ID" \
    --endpoint "$ENDPOINT" \
    --sku F0 \
    --output none
else
  az bot update \
    --name "$BOT_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --endpoint "$ENDPOINT" \
    --output none
fi

step "Enabling the Microsoft Teams channel"
az bot msteams create --name "$BOT_NAME" --resource-group "$RESOURCE_GROUP" --output none

step "Building the Teams app package"
uv run python scripts/build_teams_package.py "$APP_ID"

printf '\n\033[1;32m✓ Deployed.\033[0m\n'
cat <<EOF

  Messaging endpoint : $ENDPOINT
  Health check       : https://${FUNCTION_APP}.azurewebsites.net/api/healthz
  Bot app id         : $APP_ID
  Teams package      : appPackage/agentforge-teams.zip

Next:
  1. curl the health check above — it should report "status": "ok".
  2. In Teams: Apps → Manage your apps → Upload a custom app → pick the zip.
  3. Message the bot.

Logs:  az webapp log tail --name $FUNCTION_APP --resource-group $RESOURCE_GROUP
EOF
