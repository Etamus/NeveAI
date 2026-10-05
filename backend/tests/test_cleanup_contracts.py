import ast
from pathlib import Path
import tomllib
import unittest
import warnings

from fastapi.testclient import TestClient

from neveai.main import app
from neveai.utils.task import get_task_model_id


ROOT = Path(__file__).resolve().parents[2]


class CleanupContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            cls.paths = app.openapi()["paths"]

    def test_private_chat_and_media_routes_remain_available(self):
        required = (
            "/api/v1/chats/new",
            "/api/v1/chats/{id}/clone",
            "/api/v1/files/",
            "/api/v1/files/{id}/data/content/update",
            "/api/v1/tools/",
            "/api/v1/tools/id/{id}/valves/update",
            "/api/v1/skills/list",
            "/api/v1/knowledge/search",
            "/api/v1/knowledge/search/files",
            "/api/v1/knowledge/{id}",
            "/api/v1/stable-diffusion/generate",
            "/api/v1/music-generation/status",
            "/api/v1/video-generation/status",
            "/api/v1/auths/noauth",
            "/api/v1/auths/update/profile",
        )
        for path in required:
            with self.subTest(path=path):
                self.assertIn(path, self.paths)

    def test_public_sharing_and_unused_administration_are_not_exposed(self):
        removed = (
            "/api/v1/chats/shared",
            "/api/v1/chats/share/{share_id}",
            "/api/v1/chats/{id}/share",
            "/api/v1/chats/{id}/clone/shared",
            "/api/v1/groups/",
            "/api/v1/tools/create",
            "/api/v1/tools/load/url",
            "/api/v1/knowledge/create",
            "/api/v1/skills/create",
            "/api/v1/chats/stats/usage",
            "/api/v1/utils/gravatar",
            "/api/v1/utils/pdf",
            "/api/v1/utils/db/download",
        )
        for path in removed:
            with self.subTest(path=path):
                self.assertNotIn(path, self.paths)

    def test_application_config_and_model_catalog_still_respond(self):
        client = TestClient(app)
        for path in ("/health", "/api/config", "/llamacpp/models"):
            with self.subTest(path=path):
                response = client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIsInstance(response.json(), dict)
        self.assertNotIn(
            "enable_community_sharing", client.get("/api/config").json()["features"]
        )

    def test_local_task_selection_keeps_valid_override_and_fallback(self):
        models = {"local/chat": {}, "local/tasks": {}}
        self.assertEqual(
            get_task_model_id("local/chat", "local/tasks", models), "local/tasks"
        )
        for task_model in (None, "", "local/missing"):
            with self.subTest(task_model=task_model):
                self.assertEqual(
                    get_task_model_id("local/chat", task_model, models), "local/chat"
                )

    def test_all_task_call_sites_use_the_local_contract(self):
        for relative in ("routers/tasks.py", "utils/middleware.py"):
            tree = ast.parse((ROOT / "backend/neveai" / relative).read_text(encoding="utf-8"))
            calls = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "get_task_model_id"
            ]
            self.assertTrue(calls)
            for call in calls:
                with self.subTest(file=relative, line=call.lineno):
                    self.assertEqual(len(call.args), 3)

    def test_packaging_references_existing_artifacts(self):
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertTrue((ROOT / config["project"]["license"]["file"]).is_file())
        hatch = config["tool"]["hatch"]["build"]
        self.assertNotIn("custom", hatch.get("hooks", {}))
        self.assertEqual(hatch["targets"]["wheel"]["packages"], ["backend/neveai"])


if __name__ == "__main__":
    unittest.main()
