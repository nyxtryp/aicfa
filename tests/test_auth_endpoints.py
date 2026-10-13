import unittest
from types import SimpleNamespace

from app.main import auth_login


class FakeRequest:
    def __init__(self, body, host):
        self._body = body
        self.client = SimpleNamespace(host=host)

    async def json(self):
        return self._body


class AuthEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_rejects_non_object_json(self):
        for index, body in enumerate(([], "password", 42, None)):
            with self.subTest(body=body):
                response = await auth_login(FakeRequest(body, f"malformed-json-test-{index}"))
                self.assertEqual(response.status_code, 400)
                self.assertIn(b"invalid request", response.body)


if __name__ == "__main__":
    unittest.main()
