# Image prompt translation
- `backend/neveai/routers/stable_diffusion.py` prepares all image prompts via `deep-translator` to English before `sd-cli`.
- Current local image runtime: `leejet/Z-Image-Turbo-GGUF` `z_image_turbo-Q4_0.gguf` + `unsloth/Qwen3-4B-Instruct-2507-GGUF` `Qwen3-4B-Instruct-2507-Q4_K_M.gguf` + `black-forest-labs/FLUX.1-schnell` `ae.safetensors`; defaults 768x768, 8 steps, CFG 1.0, `--diffusion-fa`, `--offload-to-cpu`.
- Chat img2img uses only the current `metadata.parent_message`/last user image attachment; backend converts data URI/file-id/http image refs to temporary PNG and passes `--init-img` + `--strength 0.55` to `sd-cli`. Without an attached image, keep normal txt2img.
- Do not silently fall back to Portuguese for non-English prompts; failed translation should raise a clear error to avoid wrong images.
- `backend/neveai/utils/middleware.py::_collect_stable_diffusion_prompt` must prefer `metadata.parent_message`/current user prompt; do not join prior image generations because assistant image responses are empty and that mixes old prompts.
- Keep English prompts untouched in `_prepare_image_prompt`; only translate non-English/Portuguese prompts, using `source="pt"` for Portuguese.
- If both `image_generation` and `stable_diffusion` feature flags arrive true, backend should prioritize stable diffusion and skip the generic image handler.
- Translated prompts only get conservative/source-aware artifact fixes; never rewrite English direct prompts or add prompt-specific style details.


- Validate with `backend\neveai\venv\Scripts\python.exe -m py_compile backend\neveai\routers\stable_diffusion.py backend\neveai\utils\middleware.py`.