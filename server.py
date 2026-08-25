"""
Klar Channel-Data MCP Connector
================================

A minimal MCP (Model Context Protocol) server that wraps Klar's
(getklar.com) Attribution API so it can be registered as a **Custom
Connector** in the Havea Claude organization.

Why this exists
----------------
Claude's cloud sandbox (used for chats and scheduled/background tasks) can
only reach a small fixed allowlist of domains directly (npm, pypi, etc.) —
this is a fixed platform limitation, not something an org admin can change.
Third-party APIs like Klar's therefore cannot be called with a raw
bash/curl script from inside a Claude session or scheduled task.

MCP connectors are different: when Claude calls a *connector* tool, the
actual HTTP request is made by the connector's own server (this file, once
deployed and reachable over HTTPS) — not by Claude's sandboxed bash. That's
why wrapping the Klar API behind a small always-on server and registering
it as a custom connector makes it reachable from any chat *and* from daily
scheduled tasks, independent of whether anyone's laptop is on.

What this server exposes
-------------------------
One tool, `get_channel_attribution`, which returns per-channel numbers
(orders, gross/net revenue, cost, clicks, impressions) for a date range —
exactly the "Zahlen über Kanäle" the daily Slack update needs.

Posting to Slack is intentionally NOT part of this server: Havea already
has an official, installed Slack connector, so the scheduled task should
call this connector for the Klar numbers and the existing Slack connector
to post the message. Keeping this server single-purpose keeps the attack
surface (and the secrets it holds) as small as possible.

IMPORTANT — before deploying
-----------------------------
1. The Klar API key that was pasted into a Claude chat during setup
   (`klar_pk_...cf1ed2f77971c590`, named "Reporting Elli" in the Klar
   dashboard) has been exposed in that conversation's history multiple
   times. Rotate / revoke it in the Klar dashboard (Account Settings ->
   API Keys) and generate a fresh one, then use only the NEW value as
   `KLAR_API_TOKEN` below. Never commit the real key into source control —
   set it as an environment variable / secret on whatever platform hosts
   this server.

2. Auth flow — CONFIRMED live against a real Klar account (2026-08-25):
   the long-lived API key from the dashboard is NOT used directly as a
   Bearer token (a direct call to /public/attribution with it returns 401
   Unauthorized). It must first be exchanged for a short-lived (5 minute)
   access token via `POST /public/auth/token`, passing the API key in a
   header literally named `token` (not `Authorization`, not a JSON body
   field — confirmed by Klar's own error message: "Long-lived token not
   found in headers please ensure you use \"token\" as the header key").
   The exact field name of the returned access token in that response
   body was NOT verified live (the verification browser hit a same-origin
   CORS block that only applies to browser calls — irrelevant here, since
   this server calls the API directly). The code below tries the most
   likely field names in order; if none match, it raises with the raw
   response body so the actual shape is visible in the first real test.

3. Install dependencies and run once locally (`python server.py`) to make
   sure the tool call succeeds against real Klar data before deploying.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx
from mcp.server.fastmcp import FastMCP

KLAR_API_BASE = "https://api.getklar.com"

mcp = FastMCP("klar-channel-data")


async def _get_bearer_token(client: httpx.AsyncClient) -> str:
    """Exchange the long-lived Klar API key for a short-lived Bearer token.

    See point 2 in the module docstring: the header must be named `token`,
    not `Authorization` — this was confirmed against Klar's real API.
    """
    api_token = os.environ["KLAR_API_TOKEN"]
    resp = await client.post(
        f"{KLAR_API_BASE}/public/auth/token",
        headers={"token": api_token},
    )
    resp.raise_for_status()
    data = resp.json()
    for field in ("accessToken", "access_token", "token"):
        if field in data:
            return data[field]
    raise RuntimeError(
        f"Unexpected /public/auth/token response shape, update _get_bearer_token "
        f"to match it: {data!r}"
    )


@mcp.tool()
async def get_channel_attribution(
    start_date: str = "",
    end_date: str = "",
    metric: str = "last_touch",
    window: str = "7_day",
) -> dict:
    """Fetch per-channel performance numbers from Klar for a date range.

    Returns, per channel and day: channelName, orders, netRevenue,
    grossRevenue, cost, clicks, impressions.

    Args:
        start_date: yyyy-mm-dd. Defaults to yesterday (UTC) if omitted.
        end_date: yyyy-mm-dd. Defaults to yesterday (UTC) if omitted. Must be
            within 31 days of start_date (Klar API limit).
        metric: attribution model - one of first_touch, last_touch,
            data_driven, linear.
        window: attribution window - one of unlimited, 1_day, 7_day, 28_day.
    """
    if not start_date or not end_date:
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        start_date = start_date or yesterday
        end_date = end_date or yesterday

    async with httpx.AsyncClient(timeout=15) as client:
        token = await _get_bearer_token(client)
        resp = await client.get(
            f"{KLAR_API_BASE}/public/attribution",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "startDate": start_date,
                "endDate": end_date,
                "metric": metric,
                "window": window,
            },
        )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    # Streamable HTTP is the transport custom/remote MCP connectors use.
    # Listens on 0.0.0.0:$PORT so it can be deployed behind any HTTPS
    # reverse proxy / hosting platform that terminates TLS for you.
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
