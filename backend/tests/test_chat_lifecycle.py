import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from neveai.routers.chats import delete_chat_by_id


class ChatLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_stops_active_generation_before_removing_chat(self):
        events = []
        request = SimpleNamespace(
            app=SimpleNamespace(state=SimpleNamespace(redis=None))
        )
        user = SimpleNamespace(id="user-1", role="admin")
        chat = SimpleNamespace(meta={"tags": []})

        async def stop_tasks(redis, chat_id):
            events.append(("stop", chat_id))
            return {"status": True}

        def delete_chat(chat_id, db=None):
            events.append(("delete", chat_id))
            return True

        with (
            patch(
                "neveai.tasks.stop_item_tasks", new=AsyncMock(side_effect=stop_tasks)
            ),
            patch("neveai.routers.chats.Chats.get_chat_by_id", return_value=chat),
            patch("neveai.routers.chats.Chats.delete_orphan_tags_for_user"),
            patch(
                "neveai.routers.chats.Chats.delete_chat_by_id",
                side_effect=delete_chat,
            ),
        ):
            result = await delete_chat_by_id(request, "chat-1", user=user, db=object())

        self.assertTrue(result)
        self.assertEqual(events, [("stop", "chat-1"), ("delete", "chat-1")])


if __name__ == "__main__":
    unittest.main()
