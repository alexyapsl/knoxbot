"""AES-256 encrypt/decrypt + Base64 helpers for Knox Messenger payloads.

Per the Knox docs, message bodies are AES256-encrypted and then
Base64-encoded (and reverse for inbound messages).

The docs do not pin down the cipher mode or IV handling, so both are
configurable. Defaults: CBC with a zero IV and PKCS7 padding. If the stage
environment rejects messages, try KNOX_AES_MODE=ECB or set KNOX_AES_IV.

Key handling: the getkeys API returns a hex string. If the decoded key is
longer than 32 bytes, the first 32 bytes are used for AES-256. If it is
shorter, it is SHA-256 expanded. This can be tuned once verified on stage.
"""

from __future__ import annotations

import base64
import hashlib

from Crypto.Cipher import AES
from Crypto.Util import Padding

BLOCK_SIZE = 16  # AES block size


def derive_key(key_material: str | bytes) -> bytes:
    """Derive a 32-byte AES-256 key from the getkeys key material.

    Accepts a hex string (as returned by /key/getkeys) or raw bytes.
    """
    if isinstance(key_material, str):
        text = key_material.strip()
        try:
            raw = bytes.fromhex(text)
        except ValueError:
            # Not hex; treat as raw text bytes.
            raw = text.encode("utf-8")
    else:
        raw = key_material

    if len(raw) >= 32:
        return raw[:32]
    if len(raw) == 0:
        raise ValueError("empty encryption key material")
    # Short material: expand deterministically.
    return hashlib.sha256(raw).digest()


class KnoxCipher:
    """Encrypts/decrypts Knox Messenger message bodies."""

    def __init__(self, key: bytes, mode: str = "CBC", iv: bytes | None = None):
        if len(key) != 32:
            raise ValueError("AES-256 key must be 32 bytes")
        self.key = key
        self.mode = mode.upper()
        if self.mode not in ("CBC", "ECB"):
            raise ValueError(f"unsupported AES mode: {mode}")
        if iv is None:
            iv = bytes(BLOCK_SIZE)
        if len(iv) != BLOCK_SIZE:
            raise ValueError("IV must be 16 bytes")
        self.iv = iv

    @classmethod
    def from_hex_key(
        cls, key_hex: str, mode: str = "CBC", iv_hex: str = ""
    ) -> "KnoxCipher":
        iv = bytes.fromhex(iv_hex) if iv_hex else None
        return cls(derive_key(key_hex), mode=mode, iv=iv)

    def _cipher(self) -> AES:
        if self.mode == "ECB":
            return AES.new(self.key, AES.MODE_ECB)
        return AES.new(self.key, AES.MODE_CBC, iv=self.iv)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt a UTF-8 string; returns Base64-encoded ciphertext."""
        padded = Padding.pad(plaintext.encode("utf-8"), BLOCK_SIZE)
        ciphertext = self._cipher().encrypt(padded)
        return base64.b64encode(ciphertext).decode("ascii")

    def decrypt(self, b64_ciphertext: str) -> str:
        """Decode Base64 and decrypt; returns the UTF-8 plaintext."""
        ciphertext = base64.b64decode(b64_ciphertext)
        padded = self._cipher().decrypt(ciphertext)
        return Padding.unpad(padded, BLOCK_SIZE).decode("utf-8")
