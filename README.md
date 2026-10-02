# knoxbot

Samsung Knox Messenger bot. **V1:** when it receives a message in Knox
Messenger, it replies exactly:

> received your message, you said {your message}

Later phases will suggest meeting times using the Knox PIMS calendar API —
see [PLAN.md](PLAN.md).

## Architecture

- **Receiving:** FastAPI server exposing `POST /message`. Knox Messenger
  pushes inbound messages there (headers `botUserEmail` / `botNotiType`,
  AES256-encrypted + Base64 body with `chatMsg`, `chatroomId`, `msgType`, …).
- **Sending:** `MessengerClient` wraps the Messenger API:
  device registration (`GET /messenger/contact/api/v2.0/device/o1/reg`),
  encryption key fetch (`GET /messenger/msgctx/api/v2.0/key/getkeys`),
  and replies (`POST /messenger/message/api/v2.0/message/chatRequest`).
- **Crypto:** `knoxbot/crypto.py` — AES256 + Base64 (mode/IV configurable;
  docs don't pin this down, defaults are CBC + zero IV + PKCS7).
- **Hosting:** runs locally, exposed to Samsung's servers through a
  Cloudflare Tunnel.

## Setup

```powershell
cd knoxbot
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
copy .env.example .env   # then fill in values from Knox Dev Center
```

> Use the `py` launcher — `python`/`python3` are not on PATH on this machine.

## Run

```powershell
py -m knoxbot
```

The server listens on `KNOX_PORT` (default 8080). Without credentials it
starts in log-only mode (receives and logs, doesn't reply).

## Expose with Cloudflare Tunnel

```powershell
cloudflared tunnel --url http://localhost:8080
```

Register the resulting public URL in the Knox Dev Center as the bot's
receiving URL (`https://<tunnel-hostname>/message`). For a stable hostname,
use a named tunnel instead of the quick tunnel above.

## Offline self-test

No network calls to Samsung; uses mock transports:

```powershell
py tests/selftest.py
```

Verifies: clean imports, AES256+Base64 round-trips (CBC & ECB), the
chatRequest payload shape/headers, and that an inbound encrypted TEXT
message produces the exact echo reply.

## Project layout

```
knoxbot/
  config.py     .env / environment loading
  crypto.py     AES256 + Base64 message bodies
  messenger.py  Messenger API client (device reg, getkeys, chatRequest)
  server.py     FastAPI app: POST /message webhook
  __main__.py   py -m knoxbot entrypoint
tests/
  selftest.py   offline self-test
```

## Message handling (V1)

| Inbound `msgType` | Behaviour |
|---|---|
| `TEXT` | Echo reply: `received your message, you said {chatMsg}` |
| `MEDIA` / `RTF` / `NCUSTOM` / `ADAPTIVE_CARD` / `UPDATED_ADAPTIVE_CARD` | Acknowledged (HTTP 200), no reply |
| `botNotiType: INTRO` (bot added to room) | Acknowledged, no reply |

Rate limits (Knox side): 50 events/sec short-term, 20k events/15 min
long-term; text messages max 3,300 chars (truncated defensively).
