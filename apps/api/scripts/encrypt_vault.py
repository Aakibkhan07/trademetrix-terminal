#!/usr/bin/env python3
"""Encrypt sensitive .env values into .env.vault

Usage:
    python scripts/encrypt_vault.py <dotenv_key>
"""
import json
import sys
from pathlib import Path

SENSITIVE_KEYS = [
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_ANON_KEY",
    "SECRET_KEY",
    "ENCRYPTION_KEY",
    "RAZORPAY_KEY_ID",
    "RAZORPAY_KEY_SECRET",
    "GEMINI_API_KEY",
    "REDIS_URL",
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/encrypt_vault.py <dotenv_key>")
        sys.exit(1)

    dotenv_key = sys.argv[1]
    env_path = Path(__file__).resolve().parent.parent / ".env"

    if not env_path.exists():
        print(f"ERROR: {env_path} not found")
        sys.exit(1)

    import base64
    import hashlib

    from cryptography.fernet import Fernet

    key_bytes = base64.urlsafe_b64encode(hashlib.sha256(dotenv_key.encode()).digest())
    fernet = Fernet(key_bytes)

    with open(env_path) as f:
        lines = f.readlines()

    secrets = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("\"'")
        if k.upper() in SENSITIVE_KEYS or k.upper().startswith("SUPABASE") or k.upper().startswith("SECRET"):
            secrets[k] = fernet.encrypt(v.encode()).decode()

    vault = {
        "env": {"encrypted": [secrets]},
        "version": "1",
        "description": "Auto-generated from .env",
    }

    vault_path = env_path.parent / ".env.vault"
    with open(vault_path, "w") as f:
        json.dump(vault, f, indent=2)

    print(f"Vault written to {vault_path} ({len(secrets)} secrets encrypted)")
    print(f"Decrypt with: DOTENV_KEY={dotenv_key}")


if __name__ == "__main__":
    main()
