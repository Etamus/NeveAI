import unittest

from neveai.routers.image_fast_generation import _style_only_references


class StyleReferenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
