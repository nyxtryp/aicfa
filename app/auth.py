"""Single-user password and signed-session primitives for AICFA.

The web layer is responsible for setting secure cookie flags and enforcing
CSRF/rate limits. Passwords and signing keys are persisted outside the repo.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path
from typing import Callable

PBKDF2_ITERATIONS = 310_000
SESSION_TTL_SECONDS = 12 * 60 * 60


class AuthError(ValueError):
    """Raised when authentication state or credentials are invalid."""


class AuthStore:
    def __init__(self, data_dir: str | Path, *, clock: Callable[[], float] = time.time):
        self.data_dir = Path(data_dir)
        self.password_path = self.data_dir / "auth.json"
        self.signing_key_path = self.data_dir / "session.key"
        self._clock = clock

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.data_dir, 0o700)
        except OSError:
            pass

    @property
    def configured(self) -> bool:
        return self.password_path.is_file()

    def _write_private(self, path: Path, data: bytes) -> None:
        self._ensure_dir()
        temp = path.with_name(path.name + "." + secrets.token_hex(6) + ".tmp")
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
            os.chmod(path, 0o600)
        finally:
            try:
                temp.unlink()
            except FileNotFoundError:
                pass

    def _hash_password(self, password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)

    def set_initial_password(self, password: str, setup_token: str, expected_setup_token: str) -> None:
        if not expected_setup_token or not hmac.compare_digest(setup_token, expected_setup_token):
            raise AuthError("setup authorization failed")
        if self.configured:
            raise AuthError("password is already configured")
        self._validate_password(password)
        salt = secrets.token_bytes(16)
        record = {
            "version": 1,
            "algorithm": "pbkdf2_sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
            "digest": base64.urlsafe_b64encode(self._hash_password(password, salt)).decode("ascii"),
        }
        self._write_private(self.password_path, json.dumps(record, separators=(",", ":")).encode("utf-8"))
        self._signing_key()

    @staticmethod
    def _validate_password(password: str) -> None:
        if not isinstance(password, str) or len(password) < 12 or len(password) > 1024:
            raise AuthError("password must contain 12 to 1024 characters")

    def verify_password(self, password: str) -> bool:
        if not self.configured:
            return False
        try:
            record = json.loads(self.password_path.read_text(encoding="utf-8"))
            salt = base64.urlsafe_b64decode(record["salt"])
            expected = base64.urlsafe_b64decode(record["digest"])
            actual = self._hash_password(password, salt)
            return hmac.compare_digest(actual, expected)
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def change_password(self, current_password: str, new_password: str) -> None:
        if not self.verify_password(current_password):
            raise AuthError("current password is incorrect")
        self._validate_password(new_password)
        salt = secrets.token_bytes(16)
        record = {
            "version": 1,
            "algorithm": "pbkdf2_sha256",
            "iterations": PBKDF2_ITERATIONS,
            "salt": base64.urlsafe_b64encode(salt).decode("ascii"),
            "digest": base64.urlsafe_b64encode(self._hash_password(new_password, salt)).decode("ascii"),
        }
        self._write_private(self.password_path, json.dumps(record, separators=(",", ":")).encode("utf-8"))
        self.rotate_sessions()

    def rotate_sessions(self) -> None:
        """Invalidate all existing sessions by replacing the signing key."""
        self._write_private(self.signing_key_path, secrets.token_bytes(32))

    def _signing_key(self) -> bytes:
        self._ensure_dir()
        try:
            key = self.signing_key_path.read_bytes()
            if len(key) == 32:
                return key
        except OSError:
            pass
        key = secrets.token_bytes(32)
        self._write_private(self.signing_key_path, key)
        return key

    def create_session(self) -> str:
        if not self.configured:
            raise AuthError("password is not configured")
        expires = int(self._clock()) + SESSION_TTL_SECONDS
        payload = base64.urlsafe_b64encode(json.dumps({"exp": expires, "nonce": secrets.token_hex(8)}, separators=(",", ":")).encode()).rstrip(b"=")
        signature = hmac.new(self._signing_key(), payload, hashlib.sha256).digest()
        return payload.decode("ascii") + "." + base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")

    def verify_session(self, token: str | None) -> bool:
        if not self.configured or not token or len(token) > 2048:
            return False
        try:
            payload_text, signature_text = token.split(".", 1)
            signature = base64.urlsafe_b64decode(signature_text + "=" * (-len(signature_text) % 4))
            expected = hmac.new(self._signing_key(), payload_text.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                return False
            payload = base64.urlsafe_b64decode(payload_text + "=" * (-len(payload_text) % 4))
            data = json.loads(payload)
            expires = data["exp"]
            return isinstance(expires, int) and expires > int(self._clock())
        except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
            return False
