import tempfile
import unittest
from pathlib import Path

from app.auth import AuthError, AuthStore, SESSION_TTL_SECONDS


class AuthStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.now = [1_800_000_000.0]
        self.store = AuthStore(Path(self.temp.name) / "private", clock=lambda: self.now[0])

    def tearDown(self):
        self.temp.cleanup()

    def configure(self, password="correct horse battery staple"):
        self.store.set_initial_password(password, "one-time-setup", "one-time-setup")

    def test_setup_requires_matching_nonempty_token(self):
        with self.assertRaises(AuthError):
            self.store.set_initial_password("correct horse battery staple", "", "")
        self.assertFalse(self.store.configured)

    def test_setup_requires_long_password_and_is_one_time(self):
        with self.assertRaises(AuthError):
            self.store.set_initial_password("short", "token", "token")
        self.configure()
        with self.assertRaises(AuthError):
            self.configure("another correct password")

    def test_password_is_hashed_and_permissions_are_private(self):
        self.configure()
        record = self.store.password_path.read_text()
        self.assertNotIn("correct horse battery staple", record)
        self.assertEqual(self.store.password_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.store.signing_key_path.stat().st_mode & 0o777, 0o600)

    def test_password_verification_and_change_require_current_password(self):
        self.configure()
        self.assertTrue(self.store.verify_password("correct horse battery staple"))
        self.assertFalse(self.store.verify_password("wrong password"))
        with self.assertRaises(AuthError):
            self.store.change_password("wrong password", "new correct password")
        self.store.change_password("correct horse battery staple", "new correct password")
        self.assertFalse(self.store.verify_password("correct horse battery staple"))
        self.assertTrue(self.store.verify_password("new correct password"))

    def test_session_signature_and_expiration(self):
        self.configure()
        token = self.store.create_session()
        self.assertTrue(self.store.verify_session(token))
        self.assertFalse(self.store.verify_session(token + "x"))
        self.now[0] += SESSION_TTL_SECONDS + 1
        self.assertFalse(self.store.verify_session(token))

    def test_password_change_invalidates_old_sessions(self):
        self.configure()
        token = self.store.create_session()
        self.store.change_password("correct horse battery staple", "new correct password")
        self.assertFalse(self.store.verify_session(token))
        self.assertTrue(self.store.verify_session(self.store.create_session()))

    def test_unconfigured_store_rejects_sessions(self):
        self.assertFalse(self.store.verify_session("anything"))
        with self.assertRaises(AuthError):
            self.store.create_session()


if __name__ == "__main__":
    unittest.main()
