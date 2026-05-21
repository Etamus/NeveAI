# Z-Image-Turbo local
- Current runtime is `stable-diffusion.cpp`/`sd-cli`, not diffusers/torchao.
- Diffusion model: `leejet/Z-Image-Turbo-GGUF` / `z_image_turbo-Q4_0.gguf`.
- Text encoder: `unsloth/Qwen3-4B-Instruct-2507-GGUF` / `Qwen3-4B-Instruct-2507-Q4_K_M.gguf`.
- VAE: `black-forest-labs/FLUX.1-schnell` / `ae.safetensors`.
- Defaults: 768x768, 8 steps, CFG 1.0.
- sd-cli flags: `--diffusion-fa` and `--offload-to-cpu`; avoid old UltraReal/Anima sampler/scheduler flags.
- Img2img: current chat image attachment is normalized to temporary PNG, output dimensions preserve its aspect inside 768x768, and `sd-cli` receives `--init-img` + `--strength 0.55`.

