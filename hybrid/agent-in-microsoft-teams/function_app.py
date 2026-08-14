"""Azure Functions entry point (Python v2 programming model).

`AsgiFunctionApp` forwards the full request path to the ASGI app, and `host.json`
keeps the default `api` route prefix — so the Bot Service messaging endpoint is
`https://<app>.azurewebsites.net/api/messages`, matching the FastAPI route
exactly. The catch-all route also exposes `/api/healthz`.

Auth level is ANONYMOUS on purpose: the Bot Framework authenticates every
incoming activity itself via the JWT in the `Authorization` header (validated by
`BotFrameworkAdapter`), and the Azure Bot Service will not send an Azure
Functions host key.
"""

import azure.functions as func

from agentforge_teams.app import app as fastapi_app

app = func.AsgiFunctionApp(
    app=fastapi_app,
    http_auth_level=func.AuthLevel.ANONYMOUS,
)
