"""Rotate ENCRYPTION_KEY: decrypt all broker credentials with old key,
generate new key, update .env, re-encrypt with new key, save to DB.

Usage: python3 scripts/rotate_encryption_key.py
Run this INSIDE the API container or in the app venv.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["DOTENV_KEY"] = ""
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


async def rotate():
    from cryptography.fernet import Fernet
    from core.db import get_supabase
    from core.safe_query import async_safe_execute

    old_key = os.getenv("ENCRYPTION_KEY", "")
    if not old_key:
        print("ERROR: ENCRYPTION_KEY not found in environment")
        sys.exit(1)

    old_fernet = Fernet(old_key.encode())

    print(f"Reading broker credentials with old key: {old_key[:10]}...")
    supabase = get_supabase()
    rows = await async_safe_execute(
        supabase.table("broker_credentials").select("*")
    )
    if not rows:
        print("No broker credentials found. Nothing to re-encrypt.")
    else:
        print(f"Found {len(rows)} credential sets to re-encrypt")
        decrypted = []
        for row in rows:
            entry = {"id": row["id"]}
            for field in ("encrypted_api_key", "encrypted_secret_key", "encrypted_access_token", "encrypted_refresh_token"):
                val = row.get(field)
                if val:
                    try:
                        entry[field] = old_fernet.decrypt(val.encode()).decode()
                    except Exception as e:
                        print(f"  WARNING: failed to decrypt {field} for row {row['id']}: {e}")
                        entry[field] = val
                else:
                    entry[field] = ""
            decrypted.append(entry)

    new_key = Fernet.generate_key().decode()
    new_fernet = Fernet(new_key.encode())
    print(f"New encryption key generated: {new_key[:10]}...")

    if decrypted:
        for entry in decrypted:
            updates = {}
            for field in ("encrypted_api_key", "encrypted_secret_key", "encrypted_access_token", "encrypted_refresh_token"):
                plain = entry.get(field, "")
                if plain:
                    updates[field] = new_fernet.encrypt(plain.encode()).decode()
            if updates:
                from core.safe_query import async_safe_execute as upd
                supabase2 = get_supabase()
                await upd(
                    supabase2.table("broker_credentials").update(updates).eq("id", entry["id"])
                )
                print(f"  Re-encrypted credential {entry['id'][:8]}...")

    # Update .env file
    env_lines = []
    if env_path.exists():
        env_lines = env_path.read_text().splitlines()
    found = False
    new_env_lines = []
    for line in env_lines:
        if line.startswith("ENCRYPTION_KEY="):
            new_env_lines.append(f"ENCRYPTION_KEY={new_key}")
            found = True
        else:
            new_env_lines.append(line)
    if not found:
        new_env_lines.append(f"ENCRYPTION_KEY={new_key}")
    env_path.write_text("\n".join(new_env_lines) + "\n")
    print(f"Updated {env_path} with new ENCRYPTION_KEY")

    print("\n=== ROTATION COMPLETE ===")
    print(f"Old key (last 8 chars): ...{old_key[-8:]}")
    print(f"New key (last 8 chars): ...{new_key[-8:]}")
    print("Restart containers for the new key to take effect.")
    print("\nThen set this as a GitHub secret:")
    print(f"  gh secret set ENCRYPTION_KEY -b'{new_key}'")


asyncio.run(rotate())
