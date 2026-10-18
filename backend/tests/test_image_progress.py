import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

from neveai.utils.image_progress import initial_image_dimensions
from neveai.routers import image_quality_generation as generation
from neveai.routers import stable_diffusion as sd


class ImageProgressTests(unittest.TestCase):
    def image(self, size, orientation=None):
        output = io.BytesIO()
        image = Image.new('RGB', size)
        exif = image.getexif()
        if orientation:
            exif[274] = orientation
        image.save(output, format='PNG', exif=exif)
        return output.getvalue()

    def test_generation_without_references_keeps_selected_dimensions(self):
        with patch.object(sd, '_read_image_reference_bytes') as read:
            self.assertEqual(initial_image_dimensions(sd.QWEN_IMAGE_21_OFFICIAL_QUALITY, '9:16', [], 'me', (704, 1216)), (704, 1216))
            read.assert_not_called()

    def test_quality_preview_matches_runtime_for_landscape_portrait_and_exif(self):
        for source, orientation in [((1918, 1076), None), ((900, 1600), None), ((1600, 900), 6)]:
            for count in (1, 4, 10):
                with self.subTest(source=source, orientation=orientation, count=count), \
                        patch.object(sd, '_read_image_reference_bytes', return_value=self.image(source, orientation)) as read, \
                        patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                        patch.object(generation, '_prefer_int8_edit', return_value=True), \
                        patch.object(generation.psutil, 'virtual_memory', return_value=SimpleNamespace(total=32*1024**3)):
                    actual = initial_image_dimensions(sd.QWEN_IMAGE_21_OFFICIAL_QUALITY, 'auto', ['ref']*count, 'me', (1024, 1024))
                    size = source[::-1] if orientation == 6 else source
                    expected = generation.NeveImage21Runtime()._reference_size(*size, generation.EDIT_MODEL_FILE, 0, count, optimized_edit=True)
                    self.assertEqual(actual, expected)
                    read.assert_called_once_with('ref', 'me')

    def test_cpu_and_gguf_keep_their_existing_reference_shapes(self):
        for backend, count in [('cpu', 1), ('cpu', 4), ('cuda12', 4)]:
            with self.subTest(backend=backend, count=count), \
                    patch.object(sd, '_read_image_reference_bytes', return_value=self.image((900, 1600))), \
                    patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value=backend), \
                    patch.object(generation, '_prefer_int8_edit', return_value=False):
                runtime = generation.NeveImage21Runtime()
                runtime._cpu_mode = runtime._memory_saver = backend == 'cpu'
                expected = runtime._reference_size(900, 1600, generation.MODEL_FILE, 0, count)
                self.assertEqual(initial_image_dimensions(sd.QWEN_IMAGE_21_OFFICIAL_QUALITY, 'auto', ['ref']*count, 'me', (1, 1)), expected)

    def test_fast_edit_uses_native_reference_dimensions(self):
        from neveai.routers.image_fast_generation import _reference_size
        with patch.object(sd, '_read_image_reference_bytes', return_value=self.image((900, 1600))), \
                patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'):
            self.assertEqual(initial_image_dimensions('qwen_image_2s', 'auto', ['ref'], 'me', (1024, 1024)), _reference_size(900, 1600, 0, 1))

    def test_full_quality_mageflow_keeps_selected_format_without_reading_attachment(self):
        with patch.object(sd, '_use_lightweight_mageflow', return_value=False), \
                patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cuda12'), \
                patch.object(sd, '_read_image_reference_bytes') as read:
            self.assertEqual(initial_image_dimensions('neve_image_2', '16:9', ['ref'], 'me', (1536, 864)), (1536, 864))
            read.assert_not_called()

    def test_lightweight_mageflow_matches_fitted_reference_canvas(self):
        with patch.object(sd, '_use_lightweight_mageflow', return_value=True), \
                patch.object(sd, '_preferred_sd_cpp_windows_backend', return_value='cpu'), \
                patch.object(sd, '_read_image_reference_bytes', return_value=self.image((900, 1600))):
            expected = sd._fit_init_image_dimensions(SimpleNamespace(width=900, height=1600), *sd.lightweight_image_dimensions('16:9'), sd.MAX_IMAGE_WIDTH)
            self.assertEqual(initial_image_dimensions('neve_image_2', '16:9', ['ref'], 'me', (1536, 864)), expected)
