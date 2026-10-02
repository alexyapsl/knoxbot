"""Configuration loading for knoxbot.

All values come from environment variables (optionally via a .env file).
No secrets are hardcoded; see .env.example for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

STAGE_BASE_URL = "https://openapi.stage.samsung.net"
PROD_BASE_URL = "https://openapi.samsung.net"


@dataclass
class Config:
    """Runtime configuration for the bot."""

    # --- Knox Messenger API ---
    base_url: str = STAGE_BASE_URL
    access_token: str = ""
    system_id: str = ""
    device_id: str = ""
    bot_email: str = ""

    # Optional: pre-known encryption key (hex string from getkeys).
    # If empty, the key is fetched at startup via the getkeys API.
    encryption_key: str = ""

    # AES parameters. The docs only say "AES256 + Base64"; mode/IV must be
    # verified against the stage environment. Defaults: CBC, zero IV, PKCS7.
    aes_mode: str = "CBC"  # CBC | ECB
    aes_iv: str = ""  # hex; empty = 16 zero bytes (CBC only)

    # --- HTTP server (Receiving API) ---
    host: str = "0.0.0.0"
    port: int = 8080

    # Behaviour
    echo_enabled: bool = True

    def validate(self) -> list[str]:
        """Return a list of missing required settings (empty if OK)."""
        missing = []
        if not self.access_token:
            missing.append("KNOX_ACCESS_TOKEN")
        if not self.system_id:
            missing.append("KNOX_SYSTEM_ID")
        if not self.bot_email:
            missing.append("KNOX_BOT_EMAIL")
        return missing


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_config(env_file: str | None = ".env") -> Config:
    """Load configuration from .env (if present) and the environment."""
    if env_file:
        load_dotenv(env_file)

    env_name = os.getenv("KNOX_ENV", "stage").strip().lower()
    default_base = PROD_BASE_URL if env_name == "production" else STAGE_BASE_URL

    return Config(
        base_url=os.getenv("KNOX_BASE_URL", default_base).rstrip("/"),
        access_token=os.getenv("KNOX_ACCESS_TOKEN", "").strip(),
        system_id=os.getenv("KNOX_SYSTEM_ID", "").strip(),
        device_id=os.getenv("KNOX_DEVICE_ID", "").strip(),
        bot_email=os.getenv("KNOX_BOT_EMAIL", "").strip(),
        encryption_key=os.getenv("KNOX_ENCRYPTION_KEY", "").strip(),
        aes_mode=os.getenv("KNOX_AES_MODE", "CBC").strip().upper(),
        aes_iv=os.getenv("KNOX_AES_IV", "").strip(),
        host=os.getenv("KNOX_HOST", "0.0.0.0").strip(),
        port=int(os.getenv("KNOX_PORT", "8080")),
        echo_enabled=_bool(os.getenv("KNOX_ECHO_ENABLED"), True),
    )
