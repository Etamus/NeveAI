"""Exercise the actual attachment extraction function without changing user chats."""
import ast
import asyncio
import logging
from pathlib import Path
from types import SimpleNamespace
import unittest


class ChatAttachmentContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_branch_order_and_access_control(self):
        from neveai.retrieval.utils import get_sources_from_items
        from unittest.mock import patch
        chat = SimpleNamespace(id="source", user_id="owner", title="Source", chat={"history": {
            "currentId": "a2", "messages": {
                "u1": {"id": "u1", "role": "user", "content": "Remember cobalt-742", "parentId": None, "childrenIds": ["a1", "discarded"]},
                "a1": {"id": "a1", "role": "assistant", "content": "Stored", "parentId": "u1", "childrenIds": ["u2"]},
                "u2": {"id": "u2", "role": "user", "content": "Second", "parentId": "a1", "childrenIds": ["a2"]},
                "a2": {"id": "a2", "role": "assistant", "content": "Final", "parentId": "u2", "childrenIds": []},
                "discarded": {"id": "discarded", "role": "assistant", "content": "WRONG BRANCH", "parentId": "u1", "childrenIds": []},
            }}})
        for role, user_id, allowed in [("user", "owner", True), ("user", "other", False), ("admin", "admin", True)]:
            with patch("neveai.retrieval.utils.Chats.get_chat_by_id", return_value=chat):
                result = await get_sources_from_items(SimpleNamespace(), [{"type": "chat", "id": "source"}], ["question"], None, 3, None, 3, 0, 0, False, user=SimpleNamespace(role=role, id=user_id))
            self.assertEqual(bool(result), allowed)
            if allowed:
                text = result[0]["document"][0]
                self.assertNotIn("WRONG BRANCH", text)
                self.assertIn("cobalt-742", text)
                self.assertLess(text.index("Stored"), text.index("Second"))
                self.assertEqual(result[0]["source"]["id"], "source")


if __name__ == "__main__":
    unittest.main()
