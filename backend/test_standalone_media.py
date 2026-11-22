import asyncio
import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from neveai.utils.standalone_media import media_request


@pytest.mark.parametrize(("feature", "handler_name"), [
    ("stable_diffusion", "chat_stable_diffusion_handler"),
    ("video_generation", "chat_video_generation_handler"),
    ("model3d_generation", "chat_model3d_handler"),
])
def test_empty_catalog_dispatches_without_text_generation(feature, handler_name, monkeypatch):
    main = importlib.import_module("neveai.main")
    from neveai.utils import middleware

    config = SimpleNamespace(ENABLE_STABLE_DIFFUSION=True, ENABLE_VIDEO_GENERATION=True)
    app = SimpleNamespace(state=SimpleNamespace(config=config, MODELS={}))
    request = Request({"type": "http", "app": app, "headers": []})
    user = SimpleNamespace(id="test-user", role="admin")
    handler = AsyncMock(side_effect=lambda request, data, extra, user: data)
    llm = AsyncMock()
    catalog = AsyncMock()
    monkeypatch.setattr(main, "get_all_models", catalog)
    monkeypatch.setattr(main, "chat_completion_handler", llm)
    monkeypatch.setattr(middleware, handler_name, handler)
    asyncio.run(main.chat_completion(request, {"model": "neve-media/" + feature, "features": {feature: True},
                                               "messages": [{"role": "user", "content": "test"}]}, user))
    handler.assert_awaited_once()
    extra = handler.await_args.args[2]
    assert extra["__features__"][feature] and extra["__metadata__"]["skip_llm"]
    llm.assert_not_called()
    catalog.assert_not_called()


def test_special_ids_require_matching_enabled_feature_and_permissions():
    config = SimpleNamespace(ENABLE_STABLE_DIFFUSION=True, ENABLE_VIDEO_GENERATION=False)
    user = SimpleNamespace(role="user", id="test-user")
    with pytest.raises(ValueError):
        media_request("neve-media/video_generation", {"video_generation": True}, config, user)
    with pytest.raises(ValueError):
        media_request("neve-media/model3d_generation", {"model3d_generation": True}, config, user)
    with pytest.raises(ValueError):
        media_request("neve-media/video_generation", {"stable_diffusion": True}, config, user)
    assert media_request("normal-chat", {}, config, user) is None
