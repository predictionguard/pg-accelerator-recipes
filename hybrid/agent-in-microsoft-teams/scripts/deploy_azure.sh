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

# Captured before .env is read, so the banner below can say where APP_NAME came
# from. That distinction matters: a value exported in your shell dies with the
# terminal, one in .env doesn't.
APP_NAME_FROM_SHELL="${APP_NAME:-}"

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
# APP_NAME names every Azure resource, so use a different one per agent — and
# this script only ever updates resources whose names match it. Get it wrong and
# nothing errors: you simply provision a second, parallel deployment and leave
# the first one untouched. Hence the origin tracking and the banner further down.
if [[ -n "$APP_NAME_FROM_SHELL" ]]; then
  APP_NAME_ORIGIN="a shell export"
elif [[ -n "${APP_NAME:-}" ]]; then
  APP_NAME_ORIGIN=".env"
else
  APP_NAME_ORIGIN="the built-in default"
fi
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

# Shown before anything is created, because every name below is derived from
# APP_NAME and a wrong one fails silently — by building a second deployment.
step "Deploying as: $APP_NAME"
printf '  APP_NAME came from %s\n\n' "$APP_NAME_ORIGIN"
printf '    region          : %s\n' "$LOCATION"
printf '    resource group  : %s\n' "$RESOURCE_GROUP"
printf '    storage account : %s\n' "$STORAGE_ACCOUNT"
printf '    function app    : %s\n' "$FUNCTION_APP"
printf '    bot             : %s\n' "$BOT_NAME"

if [[ "$APP_NAME_ORIGIN" != ".env" ]]; then
  printf '\n\033[1;33m  ⚠ APP_NAME is not in .env, so it will not survive this terminal.\033[0m\n'
  printf '    A later run without it falls back to "agentforge-teams-demo" and\n'
  printf '    provisions a separate deployment rather than updating this one.\n\n'
  printf '    Make it durable:  echo "APP_NAME=%s" >> .env\n' "$APP_NAME"
fi

# Defaulting is the case that silently creates a stray deployment, so confirm it
# when a human is watching. Piped or CI runs are unaffected.
if [[ "$APP_NAME_ORIGIN" == "the built-in default" && -t 0 ]]; then
  printf '\n'
  # `|| true` because read returns non-zero at EOF (Ctrl-D, or a closed stdin),
  # and under `set -e` that would abort with no explanation at all.
  reply=""
  read -r -p "  Continue with the default name? [y/N] " reply || true
  [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]] || fail "Stopped. Set APP_NAME in .env, then re-run."
fi

# A subscription can't create a resource type until its provider namespace is
# registered, and Azure only says so at create time — so an unregistered
# Microsoft.Web surfaces as MissingSubscriptionRegistration three steps in, with
# a resource group and storage account already provisioned, and Microsoft.
# BotService not until step five. One list call up front turns two half-finished
# runs into a message you can act on. Providers stay registered, so this is a
# no-op on every subsequent deploy.
step "Checking resource providers"
REGISTERED="$(az provider list --query "[?registrationState=='Registered'].namespace" -o tsv | tr '[:upper:]' '[:lower:]')"
is_registered() { grep -qx "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" <<<"$REGISTERED"; }

MISSING=""
for ns in Microsoft.Storage Microsoft.Web Microsoft.BotService; do
  is_registered "$ns" || MISSING="$MISSING $ns"
done

# A warning rather than a gate: whether the Function App pulls in a Log
# Analytics workspace depends on how Application Insights gets provisioned, so
# failing on it would block deploys that would have worked.
is_registered Microsoft.OperationalInsights || printf '  note: Microsoft.OperationalInsights is unregistered — %s\n' \
  "register it too if Application Insights fails to provision"

if [[ -n "$MISSING" ]]; then
  printf '\n  Not registered on this subscription:%s\n\n' "$MISSING"
  for ns in $MISSING; do
    printf '    az provider register --namespace %s --wait\n' "$ns"
  done
  printf '\n'
  fail "Run the above, then re-run this script. Registering a provider is free
  and creates nothing — it only permits the subscription to use that namespace.
  It needs the */register/action permission, which Contributor includes; if it
  is denied, a subscription Owner has to run it for you."
fi
echo "  ok"

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
# Azure rejects multi-tenant bot creation outright now ("Multitenant bot creation
# is deprecated. Please use SingleTenant or UserAssignedMSI"), so the Entra app
# has to be single-tenant too — the bot resource and its app registration must
# agree on audience. AzureADMyOrg is the single-tenant value.
TENANT_ID="$(az account show --query tenantId -o tsv)"

step "Entra app registration for the bot"
APP_ID="$(az ad app list --display-name "$BOT_NAME" --query "[0].appId" -o tsv)"
if [[ -z "$APP_ID" ]]; then
  APP_ID="$(az ad app create \
    --display-name "$BOT_NAME" \
    --sign-in-audience AzureADMyOrg \
    --query appId -o tsv)"
  echo "  created app id: $APP_ID"
else
  echo "  reusing app id: $APP_ID"
  # An app registered before this script switched to single-tenant still carries
  # the old audience, and `az bot create` fails on it every time until it's
  # corrected. Idempotent, so it costs nothing on an already-correct app.
  az ad app update --id "$APP_ID" --sign-in-audience AzureADMyOrg --output none
fi

# `az ad app create` makes only the application object. A single-tenant bot also
# needs a service principal for that app in the tenant, or every outbound token
# request fails with AADSTS7000229 — and the failure mode is nasty: inbound
# activities authenticate fine and return 202, so the bot looks healthy while
# silently never replying. The error handler can't report it either, because
# posting that message needs the same token.
if [[ -z "$(az ad sp list --filter "appId eq '$APP_ID'" --query "[0].id" -o tsv 2>/dev/null)" ]]; then
  az ad sp create --id "$APP_ID" --output none
  echo "  created its service principal"
else
  echo "  service principal already present"
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
    "MicrosoftAppType=SingleTenant" \
    "MicrosoftAppId=$APP_ID" \
    "MicrosoftAppPassword=$APP_PASSWORD" \
    "MicrosoftAppTenantId=$TENANT_ID" \
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
    --app-type SingleTenant \
    --appid "$APP_ID" \
    --tenant-id "$TENANT_ID" \
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

# The package is named from TEAMS_APP_NAME by build_teams_package.py, so it is
# not knowable here — "Agent Forge" yields agent-forge-teams.zip. Read the name
# off disk rather than guessing it, which previously pointed people at a file
# that did not exist.
TEAMS_ZIP="$(ls -t appPackage/*.zip 2>/dev/null | head -1)"

printf '\n\033[1;32m✓ Deployed.\033[0m\n'
cat <<EOF

  Messaging endpoint : $ENDPOINT
  Health check       : https://${FUNCTION_APP}.azurewebsites.net/api/healthz
  Bot app id         : $APP_ID
  Teams package      : ${TEAMS_ZIP:-appPackage/ (build failed?)}

Next:
  1. curl the health check above — it should report "status": "ok".
  2. In Teams: Apps → Manage your apps → Upload a custom app → pick the zip.
  3. Message the bot.

Logs:  az webapp log tail --name $FUNCTION_APP --resource-group $RESOURCE_GROUP
EOF
