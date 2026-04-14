from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cryptography.fernet import Fernet, InvalidToken

STATE_TABLE_NAME = "encrypted_project_state"
STATE_RECORD_KEY = "active"


def _derive_fernet_key(raw_value: str) -> bytes:
    candidate = (raw_value or "").strip().encode("utf-8")
    if not candidate:
        raise ValueError("state encryption key must be non-empty")
    try:
        Fernet(candidate)
        return candidate
    except (ValueError, TypeError):
        digest = hashlib.sha256(candidate).digest()
        return base64.urlsafe_b64encode(digest)


def _load_or_create_key(output_root: Path) -> bytes:
    env_key = os.getenv("IDEA_STATE_ENCRYPTION_KEY", "").strip()
    if env_key:
        return _derive_fernet_key(env_key)

    key_path = Path(os.getenv("IDEA_STATE_ENCRYPTION_KEY_PATH", output_root / "project-state.key"))
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists():
        return _derive_fernet_key(key_path.read_text(encoding="utf-8"))

    generated_key = Fernet.generate_key()
    key_path.write_text(generated_key.decode("utf-8") + "\n", encoding="utf-8")
    key_path.chmod(0o600)
    return generated_key


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {STATE_TABLE_NAME} (
          state_key TEXT PRIMARY KEY,
          ciphertext BLOB NOT NULL,
          updated_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def _save_ciphertext(db_path: Path, ciphertext: bytes) -> None:
    updated_at = datetime.now(timezone.utc).isoformat()
    with _connect(db_path) as connection:
        connection.execute(
            f"""
            INSERT INTO {STATE_TABLE_NAME} (state_key, ciphertext, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(state_key)
            DO UPDATE SET ciphertext = excluded.ciphertext, updated_at = excluded.updated_at
            """,
            (STATE_RECORD_KEY, ciphertext, updated_at),
        )
        connection.commit()


def _load_ciphertext(db_path: Path) -> bytes | None:
    with _connect(db_path) as connection:
        row = connection.execute(
            f"SELECT ciphertext FROM {STATE_TABLE_NAME} WHERE state_key = ?",
            (STATE_RECORD_KEY,),
        ).fetchone()
    return bytes(row[0]) if row else None


def _encrypt_payload(fernet: Fernet, payload: dict[str, Any]) -> bytes:
    serialized = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
    return fernet.encrypt(serialized)


def _decrypt_payload(fernet: Fernet, ciphertext: bytes) -> dict[str, Any]:
    try:
        plaintext = fernet.decrypt(ciphertext)
    except InvalidToken as exc:
        raise RuntimeError(
            "project state decryption failed. "
            "IDEA_STATE_ENCRYPTION_KEY does not match the key used to write the state DB."
        ) from exc
    return json.loads(plaintext.decode("utf-8"))


def load_or_initialize_state(
    output_root: Path,
    legacy_json_path: Path,
    normalize_state: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    db_path = Path(os.getenv("IDEA_STATE_DB_PATH", output_root / "project-state.db"))
    fernet = Fernet(_load_or_create_key(output_root))
    ciphertext = _load_ciphertext(db_path)

    if ciphertext is not None:
        payload = normalize_state(_decrypt_payload(fernet, ciphertext))
        _save_ciphertext(db_path, _encrypt_payload(fernet, payload))
        return payload

    if legacy_json_path.exists():
        try:
            legacy_payload = json.loads(legacy_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            legacy_payload = {}
        normalized = normalize_state(legacy_payload)
        _save_ciphertext(db_path, _encrypt_payload(fernet, normalized))
        try:
            legacy_json_path.unlink()
        except OSError:
            pass
        return normalized

    normalized = normalize_state({})
    _save_ciphertext(db_path, _encrypt_payload(fernet, normalized))
    return normalized


def save_state(
    output_root: Path,
    payload: Any,
    normalize_state: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    db_path = Path(os.getenv("IDEA_STATE_DB_PATH", output_root / "project-state.db"))
    fernet = Fernet(_load_or_create_key(output_root))
    normalized = normalize_state(payload)
    _save_ciphertext(db_path, _encrypt_payload(fernet, normalized))
    return normalized
