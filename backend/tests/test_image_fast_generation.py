import unittest

from neveai.routers.image_fast_generation import (
    BASE_STEPS, LORA_FILE, MODEL_FILE, SIGMAS, TURBO_STEPS,
    NeveImage2SRuntime, _style_only_references,
)


class StyleReferenceTests(unittest.TestCase):
    def test_v03_sampling_switches_to_unmodified_base_after_seven_steps(self):
        self.assertIn("v0.3-6step-lora-r128", LORA_FILE)
        self.assertEqual((TURBO_STEPS, BASE_STEPS), (7, 2))
        self.assertEqual(len(SIGMAS.split(",")), 9)
        for refs in ([], ["first.png"], ["first.png", "second.png", "third.png"]):
            with self.subTest(references=len(refs)):
                graph = NeveImage2SRuntime.build_workflow("Uma cena", 1152, 1152, refs, 42)
                self.assertEqual(graph["1"]["inputs"]["unet_name"], MODEL_FILE)
                self.assertEqual(graph["2"]["inputs"]["strength"], 1.0)
                self.assertEqual(graph["20"]["inputs"], {"sigmas": ["10", 0], "step": 7})
                self.assertEqual(graph["11"]["inputs"]["sigmas"], ["20", 0])
                self.assertEqual(graph["24"]["inputs"]["sigmas"], ["20", 1])
                self.assertEqual(graph["24"]["inputs"]["latent_image"], ["11", 0])
                self.assertEqual(graph["21"]["class_type"], "DisableNoise")
                self.assertEqual(graph["22"]["inputs"]["model"], ["1", 0])
                self.assertEqual(graph["22"]["inputs"]["device"], "off")
                self.assertEqual(graph["23"]["inputs"]["conditioning"], ["5", 0])
                self.assertEqual(graph["12"]["inputs"]["samples"], ["24", 0])
                for node in graph.values():
                    for value in node["inputs"].values():
                        if isinstance(value, list):
                            self.assertIn(value[0], graph)

    def test_style_reference_does_not_blur_previous_subjects(self):
        prompt = (
            "Faca o personagem da imagem 1 e 2 sentados em uma mesa em um bar medieval. "
            "O estilo visual deve ser como a imagem 3"
        )
        self.assertEqual(_style_only_references(prompt, 3), {2})

    def test_style_reference_before_subjects(self):
        prompt = "A imagem 3 como referencia de estilo para os personagens da imagem 1 e 2"
        self.assertEqual(_style_only_references(prompt, 3), {2})

    def test_english_style_reference(self):
        prompt = "Use image 1 and image 2 as characters, image 3 as style"
        self.assertEqual(_style_only_references(prompt, 3), {2})

    def test_subjects_without_style_remain_untouched(self):
        self.assertEqual(_style_only_references("Misture as imagens 1 e 2", 2), set())

    def test_workflow_uses_native_reference_tokens_for_portuguese_prompt(self):
        workflow = NeveImage2SRuntime.build_workflow(
            "Use a imagem 1 como personagem e a imagem 2 como estilo",
            1152,
            1152,
            ["first.png", "second.png"],
            42,
        )

        prompt = workflow["5"]["inputs"]["prompt"]
        self.assertIn("<image1>", prompt)
        self.assertIn("<image2>", prompt)
        self.assertIn("Use a <image1> como personagem", prompt)


if __name__ == "__main__":
    unittest.main()
