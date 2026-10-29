# Knox Bot — Working Memory

Last updated: 2026-10-29 (Asia/Hong_Kong)

This note captures what we know so far about Alex's Samsung Knox Messenger bot work, including the direction change from a custom webhook server to Knox AI Builder + internal API integration.

## Current direction

- Original approach: custom FastAPI receiver (`app.py` / `knoxbot.server`) exposed through Cloudflare Tunnel.
- That approach is **on hold** because the receiving URL needs an approval process, and quick Cloudflare tunnels are ephemeral.
- Current approach: build the bot with **Knox AI Builder** using **app cards / API integration**.
- Alex's immediate goal is to register APIs to the bot and later decide whether to route requests to an external LLM such as OpenRouter.

## Bot / portal facts

- Bot ID: `sehk_axbot`.
- Bot status in Knox Dev Center: **Activate**.
- Company: `삼성전자`.
- Team: `D2C OPS & Innovation Part/SEHK`.
- Bot token expiry: `2027-10-05`.
- Do **not** commit tokens or `.env` secrets to the repo.

## Reference docs in this repo

- `docs/Knox_AI_Builder_Tutorial_v1.0_Eng.pdf` — 284-page Knox AI Builder tutorial.
- `docs/Knox_Guide_AppCard_API.pdf` — 52-page app card / API guide.
- Extracted working notes are also in `docs/` (`appcard_api_guide.txt`, `appcard_section.txt`, `section4.txt`, etc.).

## Knox AI Builder capabilities learned

- App cards are based on **Microsoft Adaptive Cards JSON**.
- Bot Builder can register external APIs with:
  - URL
  - method
  - headers
  - query/path params
  - body fields
- User inputs can be passed into API calls as `${inputId}`.
- API responses can be rendered using template variables like:
  - `${variableName}` for object fields
  - `${body[n].variableName}` for array items
- API responses can be chained into subsequent API calls.
- Builder also supports webhooks, approval flows, notifications, and button/action handling.

## Samsung reply on 2026-10-13

Samsung's answer to Alex's inquiry:

- API integration with AI Builder is currently limited to **internal company systems only**.
- Firewall request information required when integrating AI Builder with an internal system:
  - **Source:** `182.195.131.87`, `182.195.131.89`, `182.195.131.105` — quoted in the reply as `182.195.131.87, 89, 105` (AI Builder)
  - **Destination:** API IP/URL
  - **Port:** API port

Implication: public internet APIs are not directly callable from AI Builder unless Samsung later approves that path. For now, AI Builder should call an **internal relay/service** inside the Samsung network.

## Internal relay plan

A minimal relay exists in the repo at `relay.py`.

### What it does

- Runs a FastAPI service.
- Exposes:
  - `GET /healthz`
  - `GET /stock?productCodes=SM-S938BZAKTGY`
- Proxies `/stock` to Samsung Shop HK:
  - `https://shop.samsung.com/hk/servicesv2/getSimpleProductsInfo`
- Uses `httpx.AsyncClient` with `trust_env=True`, so corporate proxy env vars such as `HTTPS_PROXY` are honoured.
- Listens on `0.0.0.0:8080` by default.
- Port can be changed with `RELAY_PORT`.

### Why it exists

AI Builder can only call internal systems, so the relay should be hosted on a machine that:

1. Is reachable from AI Builder over the Samsung internal network.
2. Can itself reach the target API or public upstream through the corporate proxy/firewall.
3. Has a stable internal hostname/IP that can be registered in AI Builder.

### Hosting checklist

- Pick an internal Windows/Linux host that can stay online.
- Install Python + dependencies:
  - `fastapi`
  - `uvicorn`
  - `httpx`
- Run the relay as a service, not just an interactive terminal.
- Confirm local health check: `GET /healthz` returns `{"ok": true}`.
- Confirm stock proxy works: `GET /stock?productCodes=<known product code>`.
- Request firewall access if needed:
  - Source: AI Builder IPs listed above
  - Destination: internal relay host/IP
  - Port: relay port, e.g. `8080` or approved port `80`
- Register the internal relay URL in Knox AI Builder.
- Use app cards / response templating to render the API result.

## OpenRouter / external LLM notes

Earlier assessment: calling OpenRouter from Bot Builder is technically just an HTTPS API call, so it is feasible in principle.

Current constraint from Samsung's 2026-10-13 reply: AI Builder API integration is limited to internal company systems only.

So an external LLM path would likely need either:

- an internal relay/proxy service that AI Builder is allowed to call, or
- formal approval for the external destination, if Samsung allows that exception.

Caveats for LLM integration remain:

- AI Builder API calls are effectively stateless unless a middle service stores conversation state.
- Response templating for nested LLM output needs verification in the Builder UI.
- Streaming responses should not be assumed.
- Secrets must stay server-side in the relay; do not expose API keys to the bot/card layer.

## Older custom-server approach, kept for reference

The repo still contains the original Knox Messenger webhook scaffold:

- FastAPI receiver: `POST /message`
- AES256 + Base64 message encryption/decryption helpers
- Messenger API client for device registration, key fetch, and reply sending
- Cloudflare Tunnel instructions in `README.md`

Important caveat: this laptop previously could not reach `openapi.stage.samsung.net` over TCP 443, so full Samsung round-trip testing needs a Samsung-network machine.

If this approach is revived, use a **named Cloudflare tunnel** rather than a quick tunnel so the receiving URL is stable enough for approval/whitelist processes.

## Practical next steps

1. Host `relay.py` on a stable Samsung-internal machine.
2. Verify `/healthz` and `/stock` from that host.
3. Submit firewall request from AI Builder source IPs to the relay host/port if required.
4. Register the internal relay API in Knox AI Builder.
5. Build a simple app card that calls `/stock` and renders product/stock fields.
6. Only after that, consider an internal LLM relay for OpenRouter or another model provider.
