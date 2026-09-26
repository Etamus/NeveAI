import unittest
from unittest.mock import patch

from neveai.routers import stable_diffusion as sd


class QwenVulkanMemoryTests(unittest.TestCase):
    def test_eight_gib_amd_uses_roomier_budget_without_prefetch(self):
        with (
            patch.object(sd.os, "name", "nt"),
            patch.object(sd, "_preferred_sd_cpp_windows_backend", return_value="vulkan"),
            patch.object(sd, "_detected_gpu_vram_mib", return_value=8192),
            patch.object(sd, "preferred_vulkan_device", return_value="VULKAN0"),
        ):
            self.assertEqual(
                sd._qwen_image_memory_args(),
                [
                    "--backend", "te=cpu,vae=cpu,diffusion=vulkan0",
                    "--auto-fit", "on", "--max-vram", "6.25",
                    "--vae-tiling", "--disable-prefetch",
                ],
            )

    def test_other_gpu_budget_is_unchanged(self):
        with (
            patch.object(sd.os, "name", "nt"),
            patch.object(sd, "_preferred_sd_cpp_windows_backend", return_value="vulkan"),
            patch.object(sd, "_detected_gpu_vram_mib", return_value=4096),
            patch.object(sd, "preferred_vulkan_device", return_value="VULKAN0"),
        ):
            args = sd._qwen_image_memory_args()
            self.assertEqual(args[4:6], ["--max-vram", "2"])
            self.assertNotIn("--disable-prefetch", args)

    def test_nvidia_path_is_unchanged(self):
        with (
            patch.object(sd.os, "name", "nt"),
            patch.object(sd, "_preferred_sd_cpp_windows_backend", return_value="cuda12"),
            patch.object(sd, "_detected_gpu_vram_mib", return_value=16384),
        ):
            self.assertEqual(sd._qwen_image_memory_args(), ["--auto-fit", "on", "--vae-tiling"])

    def test_weight_preparation_failure_triggers_fallback(self):
        self.assertTrue(sd._is_vulkan_memory_failure(
            "cannot make enough memory available on Vulkan0: need 2161 MB; "
            "qwen_image_2_1 segment 2/34 failed during weight preparation"
        ))
        self.assertTrue(sd._is_vulkan_memory_failure("vk::Queue::submit: ErrorDeviceLost"))
        self.assertFalse(sd._is_vulkan_memory_failure("invalid prompt"))

    def test_cpu_retry_removes_vulkan_memory_policy(self):
        command = [
            "sd-cli", "--cfg-scale", "6", "--diffusion-fa",
            "--backend", "te=cpu,vae=cpu,diffusion=vulkan0",
            "--auto-fit", "on", "--max-vram", "6.25", "--vae-tiling",
            "--disable-prefetch", "-s", "42",
        ]
        fallback = sd._qwen_image_cpu_fallback_command(command)
        self.assertIn(["--backend", "cpu", "--auto-fit", "off", "--vae-tiling"],
                      [fallback[index:index + 5] for index in range(len(fallback))])
        self.assertNotIn("--max-vram", fallback)
        self.assertNotIn("vulkan0", fallback)


if __name__ == "__main__":
    unittest.main()
