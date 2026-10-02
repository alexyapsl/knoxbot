"""Client for the Knox Messenger API (sending side).

Flow (per Knox docs):
  1. Register device:  GET /messenger/contact/api/v2.0/device/o1/reg
       -> deviceServerID (used as x-device-id)
  2. Get message key:  GET /messenger/msgctx/api/v2.0/key/getkeys
       -> key (hex) used for AES256 encrypt/decrypt of bodies
  3. Send message:     POST /messenger/message/api/v2.0/message/chatRequest
       body is AES256-encrypted + Base64-encoded JSON:
       {"requestId": ..., "chatroomId": ...,
        "chatMessageParams": [{"msgId": ..., "msgType": 0,
                               "chatMsg": "...", "msgTtl": 7200}]}
"""

from __future__ import annotations

import itertools
import json
import logging
import time

import httpx

from .config import Config
from .crypto import KnoxCipher

logger = logging.getLogger(__name__)

DEVICE_REG_PATH = "/messenger/contact/api/v2.0/device/o1/reg"
GETKEYS_PATH = "/messenger/msgctx/api/v2.0/key/getkeys"
CHAT_REQUEST_PATH = "/messenger/message/api/v2.0/message/chatRequest"

MSG_TYPE_TEXT = 0
DEFAULT_MSG_TTL = 7200  # seconds; min 3600
MAX_TEXT_LEN = 3300

_ms_counter = itertools.count()


def _unique_ms() -> int:
    """Unique-ish millisecond ID for requestId/msgId."""
    return time.time_ns() // 1_000_000 * 1000 + (next(_ms_counter) % 1000)


class MessengerClient:
    """Wraps token/device/key management and sending messages."""

    def __init__(self, config: Config, http: httpx.Client | None = None):
        self.config = config
        self._http = http or httpx.Client(base_url=config.base_url, timeout=15.0)
        self._cipher: KnoxCipher | None = None
        if config.encryption_key:
            self.set_encryption_key(config.encryption_key)

    # -- headers ---------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.access_token}",
            "System-ID": self.config.system_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _device_headers(self) -> dict[str, str]:
        headers = self._auth_headers()
        headers["x-device-type"] = "relation"
        if self.config.device_id:
            headers["x-device-id"] = self.config.device_id
        return headers

    # -- setup steps -----------------------------------------------------

    def register_device(self) -> str:
        """Call the device registration API; stores and returns device ID."""
        resp = self._http.get(DEVICE_REG_PATH, headers=self._device_headers())
        resp.raise_for_status()
        data = resp.json()
        device_id = str(data["deviceServerID"])
        self.config.device_id = device_id
        logger.info("Registered device: deviceServerID=%s", device_id)
        return device_id

    def fetch_encryption_key(self) -> str:
        """Call getkeys; configures the cipher and returns the key hex."""
        resp = self._http.get(GETKEYS_PATH, headers=self._device_headers())
        resp.raise_for_status()
        data = resp.json()
        key_hex = data["key"]
        self.set_encryption_key(key_hex)
        logger.info("Fetched encryption key from getkeys")
        return key_hex

    def set_encryption_key(self, key_hex: str) -> None:
        self._cipher = KnoxCipher.from_hex_key(
            key_hex, mode=self.config.aes_mode, iv_hex=self.config.aes_iv
        )

    def ensure_ready(self) -> None:
        """Register device (if needed) and fetch key (if needed)."""
        if not self.config.device_id:
            self.register_device()
        if self._cipher is None:
            self.fetch_encryption_key()

    @property
    def cipher(self) -> KnoxCipher:
        if self._cipher is None:
            raise RuntimeError(
                "encryption key not set; call ensure_ready() or set "
                "KNOX_ENCRYPTION_KEY"
            )
        return self._cipher

    # -- sending ---------------------------------------------------------

    def send_text(self, chatroom_id: int, text: str) -> dict:
        """Send a plain-text message to a chatroom. Returns decrypted response."""
        if len(text) > MAX_TEXT_LEN:
            text = text[:MAX_TEXT_LEN]
            logger.warning("chatMsg truncated to %d chars", MAX_TEXT_LEN)

        request_id = _unique_ms()
        payload = {
            "requestId": request_id,
            "chatroomId": chatroom_id,
            "chatMessageParams": [
                {
                    "msgId": _unique_ms(),
                    "msgType": MSG_TYPE_TEXT,
                    "chatMsg": text,
                    "msgTtl": DEFAULT_MSG_TTL,
                }
            ],
        }
        encrypted_body = self.cipher.encrypt(json.dumps(payload))
        resp = self._http.post(
            CHAT_REQUEST_PATH,
            headers=self._device_headers(),
            content=encrypted_body,
        )
        resp.raise_for_status()

        # Response body is also encrypted; decrypt best-effort.
        try:
            return json.loads(self.cipher.decrypt(resp.text))
        except Exception:  # noqa: BLE001 - response format may vary
            logger.debug("could not decrypt chatRequest response: %r", resp.text[:200])
            return {"raw": resp.text}

    # -- lifecycle -------------------------------------------------------

    def close(self) -> None:
        self._http.close()
