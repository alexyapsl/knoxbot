"""Offline self-test for knoxbot. No network calls to Samsung.

Run:  py tests/selftest.py

Covers:
  1. Package imports cleanly.
  2. AES256 + Base64 crypto round-trips (CBC and ECB), key derivation.
  3. chatRequest payload shape + encryption (mocked HTTP transport).
  4. Webhook: inbound encrypted TEXT message produces the exact echo reply;
     non-TEXT messages are acknowledged without echo.
"""

from __future__ import annotations

import json
import os
import sys

# Ensure the repo root is importable when run as a script.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
from fastapi.testclient import TestClient

from knoxbot.config import load_config
from knoxbot.crypto import KnoxCipher, derive_key
from knoxbot.messenger import MSG_TYPE_TEXT, MessengerClient
from knoxbot.server import ECHO_TEMPLATE, create_app, parse_inbound_body

PASS = "PASS"
failed = []


def check(name: str, condition: bool) -> None:
    print(f"{'ok  ' + PASS if condition else 'xx  FAIL'}  {name}")
    if not condition:
        failed.append(name)


# --- 1. imports ----------------------------------------------------------
check("package imports cleanly", True)

# --- 2. crypto ------------------------------------------------------------
KEY_HEX = ("4cc5d9fa5d44819357618b8a8d8c21326df20fa95cd5fd6da0f9cdd030d1a9b7"
           "c31df7eb7080b9c3b62ee0348eb1d86b")

key = derive_key(KEY_HEX)
check("derive_key returns 32 bytes from 64-byte hex material", len(key) == 32)

for mode in ("CBC", "ECB"):
    cipher = KnoxCipher.from_hex_key(KEY_HEX, mode=mode)
    original = '{"chatMsg": "hello Knox \uc548\ub155", "msgType": "TEXT"}'
    blob = cipher.encrypt(original)
    check(f"{mode}: ciphertext differs from plaintext", blob != original)
    check(f"{mode}: round-trip", cipher.decrypt(blob) == original)

# --- 3. messenger client (mock transport) ---------------------------------
sent = {}


def handler(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/device/o1/reg"):
        return httpx.Response(200, json={"userID": 1, "deviceServerID": 999,
                                         "newDevice": True})
    if request.url.path.endswith("/key/getkeys"):
        return httpx.Response(200, json={"key": KEY_HEX, "channelauthkey": "00"})
    if request.url.path.endswith("/message/chatRequest"):
        sent["headers"] = dict(request.headers)
        sent["body"] = request.content.decode()
        return httpx.Response(200, text="ok")
    return httpx.Response(404)


mock_http = httpx.Client(transport=httpx.MockTransport(handler),
                         base_url="https://openapi.stage.samsung.net")

env = {
    "KNOX_ENV": "stage",
    "KNOX_ACCESS_TOKEN": "test-token",
    "KNOX_SYSTEM_ID": "TESTSYS01",
    "KNOX_BOT_EMAIL": "bot@test.local",
    "KNOX_PORT": "18080",
}
old_env = {k: os.environ.get(k) for k in env}
os.environ.update(env)
config = load_config(env_file=None)
for k, v in old_env.items():
    if v is None:
        os.environ.pop(k, None)
    else:
        os.environ[k] = v

check("config loads stage base URL",
      config.base_url == "https://openapi.stage.samsung.net")
check("config missing-list empty with full env", config.validate() == [])

client = MessengerClient(config, http=mock_http)
client.ensure_ready()
check("device registration stores device ID", config.device_id == "999")
check("cipher configured after getkeys", client._cipher is not None)

client.send_text(39884873994338304, "received your message, you said hi")
check("chatRequest hit mock", "body" in sent)
check("chatRequest auth header",
      sent["headers"].get("authorization") == "Bearer test-token")
check("chatRequest device headers",
      sent["headers"].get("x-device-id") == "999"
      and sent["headers"].get("x-device-type") == "relation")

payload = json.loads(client.cipher.decrypt(sent["body"]))
check("payload chatroomId", payload["chatroomId"] == 39884873994338304)
param = payload["chatMessageParams"][0]
check("payload msgType TEXT (0)", param["msgType"] == MSG_TYPE_TEXT)
check("payload chatMsg", param["chatMsg"] == "received your message, you said hi")

# --- 4. webhook end-to-end (mock send) ------------------------------------
inbound_cipher = KnoxCipher.from_hex_key(KEY_HEX)
echoed = {}


class FakeClient:
    _cipher = inbound_cipher

    def send_text(self, chatroom_id, text):
        echoed["chatroom_id"] = chatroom_id
        echoed["text"] = text


app = create_app(config, client=FakeClient(), cipher=inbound_cipher)
tc = TestClient(app)

inbound = {
    "sender": 753019798863483753,
    "sentTime": 1465433003086,
    "senderName": "TestUser",
    "chatType": "SINGLE",
    "chatroomId": 39884873994338304,
    "msgId": 1465433003078,
    "msgType": "TEXT",
    "chatMsg": "tttttttttt",
    "senderKnoxId": "aabbcc",
}
enc_body = inbound_cipher.encrypt(json.dumps(inbound))
r = tc.post("/message", content=enc_body,
            headers={"botUserEmail": "bot@test.local", "Content-Type": "text/plain"})
check("webhook returns 200", r.status_code == 200)
check("echo sent to the right chatroom",
      echoed.get("chatroom_id") == 39884873994338304)
check("echo text exact",
      echoed.get("text") == ECHO_TEMPLATE.format(message="tttttttttt"))

# non-TEXT acknowledged, no echo
echoed.clear()
inbound_media = dict(inbound, msgType="MEDIA")
r = tc.post("/message", content=inbound_cipher.encrypt(json.dumps(inbound_media)))
check("non-TEXT acknowledged with 200", r.status_code == 200)
check("non-TEXT not echoed", echoed == {})

# plain JSON body also accepted (local testing convenience)
r = tc.post("/message", json=inbound)
check("plain JSON inbound accepted", r.status_code == 200)

r = tc.get("/health")
check("health endpoint ok", r.status_code == 200 and r.json()["status"] == "ok")

# --- summary ---------------------------------------------------------------
print()
if failed:
    print(f"FAILED: {len(failed)} check(s): {failed}")
    sys.exit(1)
print("All checks passed.")
