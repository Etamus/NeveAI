import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from itsdangerous import TimestampSigner
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from neveai.internal.legacy_state import (
    LEGACY_SESSION_COOKIE,
    import_config_namespace,
    import_database,
)
from neveai.internal.settings import RuntimeSettings, Setting, SettingsStore
from neveai.utils.session import NeveSessionMiddleware


class SettingsCompatibilityTests(unittest.TestCase):
    def test_false_zero_and_empty_values_override_defaults(self):
        store = SettingsStore(
            {"ui": {"enabled": False, "count": 0, "items": []}}, Mock()
        )
        for key, fallback, expected in (
            ("enabled", True, False),
            ("count", 10, 0),
            ("items", [1], []),
        ):
            with self.subTest(key=key):
                entry = Setting(key, f"ui.{key}", fallback, store)
                self.assertEqual(entry.value, expected)

    def test_disabled_persistence_uses_environment_default(self):
        store = SettingsStore({"ui": {"theme": "dark"}}, Mock())
        self.assertEqual(
            Setting("THEME", "ui.theme", "light", store, False).value, "light"
        )

    def test_save_preserves_other_settings_and_document_reference(self):
        document = {"ui": {"theme": "dark"}, "models": {"selected": "local/model"}}
        persist = Mock()
        store = SettingsStore(document, persist)
        config = RuntimeSettings()
        config.theme = Setting("THEME", "ui.theme", "light", store)
        config.theme = "light"
        self.assertEqual(document["ui"]["theme"], "light")
        self.assertEqual(document["models"]["selected"], "local/model")
        self.assertIs(store.document, document)
        persist.assert_called_once_with(document)

    def test_failed_write_keeps_last_saved_value(self):
        document = {"ui": {"theme": "dark"}}
        store = SettingsStore(document, Mock(side_effect=OSError("disk full")))
        config = RuntimeSettings()
        config.theme = Setting("THEME", "ui.theme", "light", store)
        with self.assertRaises(OSError):
            config.theme = "light"
        self.assertEqual(config.theme, "dark")
        self.assertEqual(document["ui"]["theme"], "dark")

    def test_redis_read_write_and_invalid_payload(self):
        transport = Mock()
        store = SettingsStore({"ui": {"theme": "dark"}}, Mock())
        config = RuntimeSettings(transport, "neveai")
        config.theme = Setting("THEME", "ui.theme", "dark", store)
        config.theme = "light"
        transport.set.assert_called_once_with("neveai:config:theme", '"light"')
        transport.get.return_value = '"dark"'
        self.assertEqual(config.theme, "dark")
        transport.get.return_value = "invalid json"
        self.assertEqual(config.theme, "dark")

    def test_unknown_setting_raises_attribute_error(self):
        config = RuntimeSettings()
        self.assertFalse(hasattr(config, "missing"))
        with self.assertRaises(AttributeError):
            config.missing = 1

    def test_new_namespace_preserves_saved_url_and_is_idempotent(self):
        document = {"webui": {"url": "https://example.test"}, "ui": {"theme": "dark"}}
        self.assertTrue(import_config_namespace(document))
        self.assertEqual(document["neve"]["url"], "https://example.test")
        self.assertEqual(document["ui"]["theme"], "dark")
        self.assertFalse(import_config_namespace(document))

    def test_existing_new_namespace_has_priority(self):
        document = {"webui": {"url": "old"}, "neve": {"url": "new"}}
        import_config_namespace(document)
        self.assertEqual(document["neve"]["url"], "new")

    def test_database_import_never_overwrites_installed_database(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = root / "webui.db"
            old.write_bytes(b"older database")
            import_database(root)
            self.assertEqual((root / "neve.db").read_bytes(), b"older database")
            old.write_bytes(b"other database")
            import_database(root)
            self.assertEqual((root / "neve.db").read_bytes(), b"older database")
            self.assertTrue(old.exists())


class SessionCompatibilityTests(unittest.TestCase):
    def setUp(self):
        async def session(request):
            return JSONResponse(
                {"session": request.session, "token": request.cookies.get("token")}
            )

        app = Starlette(routes=[Route("/", session)])
        app.add_middleware(
            NeveSessionMiddleware, secret_key="test-key", session_cookie="neve-session"
        )
        self.client = TestClient(app)

    def signed_session(self, data):
        return (
            TimestampSigner("test-key")
            .sign(base64.b64encode(json.dumps(data).encode()))
            .decode()
        )

    def test_old_session_survives_rename_and_other_cookies_are_preserved(self):
        value = self.signed_session({"oauth_state": "preserved"})
        response = self.client.get(
            "/",
            headers={"cookie": f"{LEGACY_SESSION_COOKIE}={value}; token=test-token"},
        )
        self.assertEqual(
            response.json(),
            {"session": {"oauth_state": "preserved"}, "token": "test-token"},
        )
        self.assertTrue(response.headers["set-cookie"].startswith("neve-session="))

    def test_new_cookie_has_priority_over_old_cookie(self):
        old = self.signed_session({"value": "old"})
        new = self.signed_session({"value": "new"})
        response = self.client.get(
            "/",
            headers={"cookie": f"{LEGACY_SESSION_COOKIE}={old}; neve-session={new}"},
        )
        self.assertEqual(response.json()["session"], {"value": "new"})


if __name__ == "__main__":
    unittest.main()
