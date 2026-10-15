import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class _UpstreamEncoder:
    @classmethod
    def define_schema(cls):
        return SimpleNamespace(node_id="TextEncodeQwenImage21", display_name="Original")

    @classmethod
    def execute(
        cls, clip, prompt, negative_prompt, vae=None, resolution=1024, images=None
    ):
        positive = clip.encode_from_tokens_scheduled(
            clip.tokenize(prompt, images=images)
        )
        negative = clip.encode_from_tokens_scheduled(
            clip.tokenize(negative_prompt, images=images)
        )
        return (
            positive,
            negative,
            {"vae": vae, "resolution": resolution, "images": images},
        )


def _load_extension():
    api = ModuleType("comfy_api.latest")
    api.ComfyExtension = object
    nodes = ModuleType("comfy_extras.nodes_qwen")
    nodes.TextEncodeQwenImage21 = _UpstreamEncoder
    source = (
        Path(__file__).resolve().parents[1] / "neveai/utils/image_quality_cfg1_node.py"
    )
    spec = importlib.util.spec_from_file_location("cfg1_extension_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        "sys.modules",
        {
            "comfy_api": ModuleType("comfy_api"),
            "comfy_api.latest": api,
            "comfy_extras": ModuleType("comfy_extras"),
            "comfy_extras.nodes_qwen": nodes,
        },
    ):
        spec.loader.exec_module(module)
    return module


class CFG1EncoderTests(unittest.TestCase):
    def test_positive_is_unchanged_and_duplicate_vision_pass_is_skipped(self):
        module = _load_extension()
        conditioning, tokens, images, vae = (
            object(),
            {"positive": [1, 2]},
            {"image_1": object()},
            object(),
        )
        clip = SimpleNamespace(
            tokenize=Mock(return_value=tokens),
            encode_from_tokens_scheduled=Mock(return_value=conditioning),
        )
        positive, negative, latent = module.NeveTextEncodeQwenImage21CFG1.execute(
            clip, "Edit <image1>", "", vae, 0, images
        )
        self.assertIs(positive, conditioning)
        self.assertIs(negative, conditioning)
        clip.tokenize.assert_called_once_with("Edit <image1>", images=images)
        clip.encode_from_tokens_scheduled.assert_called_once_with(tokens)
        self.assertEqual(latent, {"vae": vae, "resolution": 0, "images": images})

    def test_proxy_is_local_to_each_execution_and_delegates_model_attributes(self):
        module = _load_extension()
        clip = SimpleNamespace(
            model=object(),
            tokenize=Mock(side_effect=lambda text, **kwargs: {"text": text}),
            encode_from_tokens_scheduled=Mock(side_effect=lambda tokens: [tokens]),
        )
        self.assertIs(module._PositiveOnlyClip(clip).model, clip.model)
        first = module.NeveTextEncodeQwenImage21CFG1.execute(clip, "First", "")
        second = module.NeveTextEncodeQwenImage21CFG1.execute(clip, "Second", "")
        self.assertNotEqual(first[0], second[0])
        self.assertEqual(clip.tokenize.call_count, 2)
        self.assertEqual(clip.encode_from_tokens_scheduled.call_count, 2)
        self.assertEqual(
            _UpstreamEncoder.define_schema().node_id, "TextEncodeQwenImage21"
        )
        self.assertEqual(
            module.NeveTextEncodeQwenImage21CFG1.define_schema().node_id,
            "NeveTextEncodeQwenImage21CFG1",
        )


if __name__ == "__main__":
    unittest.main()
