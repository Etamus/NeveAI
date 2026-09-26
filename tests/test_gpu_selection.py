import unittest
from unittest.mock import patch

from neveai.utils import gpu_selection


class GpuSelectionTests(unittest.TestCase):
    def test_prefers_dedicated_amd_even_when_integrated_is_first(self):
        adapters = [
            {"Name": "AMD Radeon(TM) RX Vega 11 Graphics", "AdapterRAM": 2 * 1024**3},
            {"Name": "AMD Radeon RX 580 2048SP", "AdapterRAM": 4 * 1024**3},
        ]
        with patch.object(gpu_selection, "windows_display_adapters", return_value=adapters):
            self.assertEqual(
                gpu_selection.preferred_amd_adapter()["Name"],
                "AMD Radeon RX 580 2048SP",
            )

    def test_integrated_amd_is_used_when_it_is_the_only_adapter(self):
        adapter = {"Name": "AMD Radeon(TM) RX Vega 11 Graphics", "AdapterRAM": 2 * 1024**3}
        with patch.object(gpu_selection, "windows_display_adapters", return_value=[adapter]):
            self.assertEqual(gpu_selection.preferred_amd_adapter(), adapter)

    def test_selects_dedicated_device_from_sd_cli_and_llama_lists(self):
        outputs = [
            "VULKAN0\tAMD Radeon(TM) RX Vega 11 Graphics\n"
            "VULKAN1\tAMD Radeon RX 580 2048SP",
            "Available devices:\n"
            "  Vulkan0: AMD Radeon(TM) RX Vega 11 Graphics (2048 MiB)\n"
            "  Vulkan1: AMD Radeon RX 580 2048SP (4096 MiB)",
        ]
        for output in outputs:
            with self.subTest(output=output):
                self.assertEqual(
                    gpu_selection.select_vulkan_device(output, "AMD Radeon RX 580 2048SP").lower(),
                    "vulkan1",
                )

    def test_integrated_vulkan_is_used_when_it_is_the_only_device(self):
        self.assertEqual(
            gpu_selection.select_vulkan_device("VULKAN0\tAMD Radeon(TM) RX Vega 11 Graphics"),
            "VULKAN0",
        )


if __name__ == "__main__":
    unittest.main()
