"""ComfyUI extension for Neve Image 2.6's fixed CFG=1 edit workflows."""

from comfy_api.latest import ComfyExtension
from comfy_extras.nodes_qwen import TextEncodeQwenImage21


class _PositiveOnlyClip:
    def __init__(self, clip):
        self._clip = clip
        self._tokens = None
        self._conditioning = None

    def tokenize(self, *args, **kwargs):
        if self._tokens is None:
            self._tokens = self._clip.tokenize(*args, **kwargs)
        return self._tokens

    def encode_from_tokens_scheduled(self, *args, **kwargs):
        if self._conditioning is None:
            self._conditioning = self._clip.encode_from_tokens_scheduled(
                *args, **kwargs
            )
        return self._conditioning

    def __getattr__(self, name):
        return getattr(self._clip, name)


class NeveTextEncodeQwenImage21CFG1(TextEncodeQwenImage21):
    @classmethod
    def define_schema(cls):
        schema = super().define_schema()
        schema.node_id = "NeveTextEncodeQwenImage21CFG1"
        schema.display_name = "Neve Qwen Image 2.1 CFG1"
        return schema

    @classmethod
    def execute(
        cls, clip, prompt, negative_prompt, vae=None, resolution=1024, images=None
    ):
        # CFG=1 does not use the negative branch. Keep upstream image/VAE handling.
        return TextEncodeQwenImage21.execute(
            _PositiveOnlyClip(clip), prompt, negative_prompt, vae, resolution, images
        )


class NeveImage21CFG1Extension(ComfyExtension):
    async def get_node_list(self):
        return [NeveTextEncodeQwenImage21CFG1]


async def comfy_entrypoint():
    return NeveImage21CFG1Extension()
