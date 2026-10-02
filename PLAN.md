# Knox Bot — Project Plan

## Goal

A Samsung Knox Messenger bot that suggests meeting times. **V1 (this
scaffold):** receive any message and reply exactly
`received your message, you said {user message}`.

## Architecture

```
Knox Messenger user
      │  chat message
      ▼
Samsung Knox Messenger server ──push──►  POST https://<tunnel>/message
      ▲                                  (knoxbot FastAPI app, local machine)
      │                                       │ decrypt (AES256+Base64)
      │                                       │ parse chatMsg / chatroomId
      │                                       ▼
      └──reply── POST /messenger/message/api/v2.0/message/chatRequest
                 (body AES256-encrypted + Base64, echo text)
```

- **Receiving:** Knox pushes to `http://[server]/message`. We serve this
  with FastAPI (`knoxbot/server.py`). Headers: `botUserEmail`,
  `botNotiType`. Encrypted body fields: `sender`, `sentTime`, `senderName`,
  `chatType` (SINGLE/GROUP/BROADCAST_*), `chatroomId`, `msgId`, `msgType`
  (TEXT/MEDIA/RTF/NCUSTOM/ADAPTIVE_CARD/UPDATED_ADAPTIVE_CARD), `chatMsg`,
  `senderKnoxId`.
- **Sending:** `knoxbot/messenger.py` wraps:
  1. `GET /messenger/contact/api/v2.0/device/o1/reg` → device ID
     (`x-device-id` header, `x-device-type: relation`)
  2. `GET /messenger/msgctx/api/v2.0/key/getkeys` → AES message key (hex)
  3. `POST /messenger/message/api/v2.0/message/chatRequest` → replies
     (body: `{requestId, chatroomId, chatMessageParams: [{msgId, msgType: 0,
     chatMsg, msgTtl}]}`, encrypted)
- **Crypto:** bodies are AES256-encrypted then Base64-encoded, both
  directions. Docs don't specify mode/IV — defaults are CBC + zero IV +
  PKCS7, tunable via `KNOX_AES_MODE` / `KNOX_AES_IV` once verified on stage.
- **Hosting:** the bot runs on the local machine; a **Cloudflare Tunnel**
  (`cloudflared`) exposes `POST /message` to Samsung's servers over HTTPS.

## Constraints (from Samsung docs)

- Rate limits: 50 events/sec short-term (1s block), 20k events/15 min
  long-term (12h block).
- Text messages: max 3,300 chars.
- Base URLs: stage `openapi.stage.samsung.net`, prod `openapi.samsung.net`.

## Phases

| Phase | Scope | Status |
|---|---|---|
| 1 | Scaffold: config, crypto, messenger client, webhook, echo reply | ✅ this commit |
| 2 | Verify against **stage**: AES mode/IV, device reg, real echo in Messenger | pending (needs Dev Center setup) |
| 3 | Hardening: retries/backoff for rate limits, structured logging, named Cloudflare tunnel, INTRO greeting | pending |
| 4 | Production interface request + deploy permission | pending |
| 5 | **Meeting-time suggestions:** PIMS calendar API (`GET /pims/calendar/api/v2.0/schedules` per attendee, `targetId`/`targetLoginId`/`targetEmail`), employee lookup (`POST /employee/api/v2.0/employees`) to resolve names → EPID/loginId, optional meeting-room availability (`/pims/calendar/api/v2.0/resource/meetingroom/...`), Adaptive Card slot picker | future |

## What Alex must do in Knox Dev Center

1. **Create the bot account** — Dev Center → My Interfaces → Bot → Bot
   Management → "Request Bot Account". (One account works for both stage
   and production.)
2. **Request the Stage Bot Interface** — My Interfaces → Bot → request the
   Stage interface. Once approved, copy the **access token** and
   **System ID**.
3. **Register the receiving URL** — run the bot + Cloudflare Tunnel, then
   register `https://<tunnel-hostname>/message` as the bot's receiving
   endpoint.
4. **Firewall requests** (if the machine is behind the corporate firewall):
   - Outbound: `openapi.stage.samsung.net` (203.254.214.131) : 443
   - Inbound (stage Messenger servers): 112.106.197.161, 112.106.197.162
   - (Production later: `openapi.samsung.net` 112.107.220.134 : 443;
     inbound 182.195.35.14-16)
   - Firewall registration on the Samsung side takes 2–3 business days.
5. **Request permission / deploy** — My Interfaces → Bot → Bot Management →
   Request Permission. Own department = instant; company-wide needs
   approval.
6. **Test on stage**, then repeat steps 2/4/5 for **Production**.

## Config values needed from the portal

| `.env` key | Source |
|---|---|
| `KNOX_ACCESS_TOKEN` | Issued when the Bot Interface request is approved |
| `KNOX_SYSTEM_ID` | Shown with the bot interface in Dev Center |
| `KNOX_BOT_EMAIL` | The bot account's email (`botUserEmail`) |
| `KNOX_DEVICE_ID` | Optional — auto-registered at startup if blank |
| `KNOX_ENCRYPTION_KEY` | Optional — auto-fetched via getkeys if blank |

## Open questions to verify on stage

- Exact AES mode/IV for message bodies (defaults: CBC + zero IV + PKCS7).
- Whether the 64-byte getkeys hex material uses its first 32 bytes as the
  AES-256 key (current assumption in `crypto.derive_key`).
- Inbound body framing on the wire (assumed: raw Base64 ciphertext,
  `Content-Type: text/plain`; the server also accepts plain JSON for local
  testing).
