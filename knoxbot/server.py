"""Receiving API server: FastAPI app exposing POST /message.

Knox Messenger pushes inbound messages to http://[server]/message with:
  Headers: botUserEmail (bot account email), botNotiType (e.g. INTRO)
  Body:    AES256-encrypted + Base64 JSON with fields:
           sender, sentTime, senderName, chatType, chatroomId, msgId,
           msgType, chatMsg, senderKnoxId

V1 behaviour: for msgType TEXT, reply via chatRequest with exactly
"received your message, you said {chatMsg}". Other message types are
acknowledged (HTTP 200) without an echo.
"""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request, Response

from .config import Config
from .crypto import KnoxCipher
from .messenger import MessengerClient

logger = logging.getLogger(__name__)

ECHO_TEMPLATE = "received your message, you said {message}"


def parse_inbound_body(raw: bytes, cipher: KnoxCipher | None) -> dict:
    """Parse the inbound body.

    Normally the body is Base64(AES256(JSON)). For local testing we also
    accept plain JSON.
    """
    text = raw.decode("utf-8", errors="replace").strip()
    if cipher is not None:
        try:
            return json.loads(cipher.decrypt(text))
        except Exception:  # noqa: BLE001 - fall through to plain JSON
            logger.debug("body did not decrypt; trying plain JSON")
    return json.loads(text)


def create_app(
    config: Config,
    client: MessengerClient | None = None,
    cipher: KnoxCipher | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    `client` may be None (e.g. before credentials exist) — inbound messages
    are then logged but no reply is sent. `cipher` overrides the client's
    cipher for inbound decryption (useful in tests).
    """
    app = FastAPI(title="knoxbot", version="0.1.0")

    def inbound_cipher() -> KnoxCipher | None:
        if cipher is not None:
            return cipher
        if client is not None and client._cipher is not None:  # noqa: SLF001
            return client._cipher  # noqa: SLF001
        return None

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "bot": config.bot_email or None}

    @app.post("/message")
    async def receive_message(request: Request) -> Response:
        bot_email = request.headers.get("botUserEmail", "")
        noti_type = request.headers.get("botNotiType", "")
        raw = await request.body()

        try:
            msg = parse_inbound_body(raw, inbound_cipher())
        except Exception:  # noqa: BLE001
            logger.exception("failed to parse inbound message body")
            # Still 200: Knox retries on non-200, and a malformed body
            # will never succeed on retry.
            return Response(status_code=200)

        sender_name = msg.get("senderName", "")
        chat_type = msg.get("chatType", "")
        msg_type = (msg.get("msgType") or "").upper()
        chatroom_id = msg.get("chatroomId")
        chat_msg = msg.get("chatMsg", "")

        logger.info(
            "inbound message: bot=%s noti=%s type=%s chatType=%s "
            "chatroom=%s from=%s",
            bot_email, noti_type, msg_type, chat_type, chatroom_id,
            sender_name,
        )

        if noti_type.upper() == "INTRO":
            # Bot was added to a room via createChatroomRequest; nothing to
            # echo in V1.
            return Response(status_code=200)

        if msg_type != "TEXT":
            logger.info("acknowledging non-TEXT message type %s", msg_type)
            return Response(status_code=200)

        if not config.echo_enabled or chatroom_id is None:
            return Response(status_code=200)

        if client is None:
            logger.warning("no messenger client configured; cannot echo")
            return Response(status_code=200)

        reply = ECHO_TEMPLATE.format(message=chat_msg)
        try:
            client.send_text(int(chatroom_id), reply)
            logger.info("echoed message back to chatroom %s", chatroom_id)
        except Exception:  # noqa: BLE001
            logger.exception("failed to send echo reply")

        return Response(status_code=200)

    return app
