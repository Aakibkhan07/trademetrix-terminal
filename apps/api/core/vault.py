import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class EnvVault:
    DOTENV_KEY_ENV = "DOTENV_KEY"
    VAULT_FILE = ".env.vault"

    def __init__(self, vault_path: str | None = None):
        self.vault_path = vault_path or os.environ.get(
            "ENV_VAULT_PATH",
            str(Path(__file__).resolve().parent.parent / self.VAULT_FILE),
        )
        self._secrets: dict[str, str] = {}
        self._loaded = False

    def load(self) -> bool:
        dotenv_key = os.environ.get(self.DOTENV_KEY_ENV)
        if not dotenv_key:
            return False

        vault_file = Path(self.vault_path)
        if not vault_file.exists():
            logger.warning("Vault file %s not found", self.vault_path)
            return False

        try:
            from cryptography.fernet import Fernet

            with open(vault_file) as f:
                vault_data = json.load(f)

            env = vault_data.get("env", {})
            encrypted = env.get("encrypted", [])

            key = Fernet(dotenv_key.encode() if len(dotenv_key) == 44 else _derive_key(dotenv_key))
            for entry in encrypted:
                for k, v in entry.items():
                    try:
                        decrypted = key.decrypt(v.encode()).decode()
                        self._secrets[k] = decrypted
                    except Exception:
                        logger.warning("Failed to decrypt vault key: %s", k)

            self._loaded = True
            logger.info("Loaded %d secrets from vault", len(self._secrets))
            return True

        except Exception as e:
            logger.warning("Failed to load vault: %s", e)
            return False

    def get(self, key: str, default: str = "") -> str:
        return self._secrets.get(key, os.environ.get(key, default))

    def is_loaded(self) -> bool:
        return self._loaded


def _derive_key(raw: str) -> bytes:
    import base64
    import hashlib
    return base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())


env_vault = EnvVault()


def init_vault() -> bool:
    return env_vault.load()
