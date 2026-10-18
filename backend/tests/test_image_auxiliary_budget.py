import unittest
from unittest.mock import AsyncMock, patch

from neveai.routers import image_quality_generation as quality


class AuxiliaryBudgetTests(unittest.IsolatedAsyncioTestCase):
    def test_equal_large_sources_share_budget_for_four_to_ten_attachments(self):
        for count in range(3, 10):
            result = quality._adaptive_auxiliary_sizes([(4096, 4096)] * count)
            self.assertEqual(len(set(result)), 1)
            self.assertLessEqual(sum(w * h for w, h in result), quality.ADAPTIVE_AUXILIARY_PIXELS)
            for width, height in result:
                self.assertEqual(width, height)
                self.assertEqual(width % 32, 0)
                self.assertLessEqual(width * height, quality.MAX_AUXILIARY_PIXELS)
                self.assertGreater(width * height, quality.BALANCED_AUXILIARY_PIXELS / count * .85)

    def test_small_sources_release_budget_without_upscaling(self):
        sizes = [(145, 221), (186, 266), (2048, 2048)]
        result = quality._adaptive_auxiliary_sizes(sizes)
        self.assertEqual(result[:2], [(128, 192), (160, 224)])
        self.assertEqual(result[2], (864, 864))
        self.assertLessEqual(sum(w * h for w, h in result), quality.ADAPTIVE_AUXILIARY_PIXELS)

    def test_unused_small_share_is_redistributed_equally_to_other_images(self):
        result = quality._adaptive_auxiliary_sizes([(128, 128), (4096, 4096), (4096, 4096)])
        self.assertEqual(result[0], (128, 128))
        self.assertEqual(result[1], result[2])
        self.assertGreater(result[1][0] ** 2, quality.ADAPTIVE_AUXILIARY_PIXELS / 3)

    def test_tiny_portrait_alignment_does_not_squash_the_face(self):
        for width, height in [(145, 221), (186, 266), (266, 186), (221, 145)]:
            fitted = quality._adaptive_auxiliary_sizes([(width, height)])[0]
            self.assertLess(abs((fitted[0] / fitted[1]) / (width / height) - 1), .03)

    def test_order_does_not_change_allocation_and_wide_images_remain_bounded(self):
        sizes = [(2048, 1536), (186, 266), (10000, 100), (1024, 2048)]
        result = quality._adaptive_auxiliary_sizes(sizes)
        self.assertEqual(result[::-1], quality._adaptive_auxiliary_sizes(sizes[::-1]))
        for width, height in result:
            self.assertLessEqual(max(width, height), quality.BALANCED_MAX_SIDE)
        self.assertLessEqual(sum(w * h for w, h in result), quality.ADAPTIVE_AUXILIARY_PIXELS)

    def test_invalid_dimensions_are_rejected(self):
        for sizes in ([], [(0, 100)], [(100, -1)]):
            with self.assertRaises(ValueError):
                quality._adaptive_auxiliary_sizes(sizes)

    async def test_oom_retries_old_auxiliary_budget_before_switching_model(self):
        runtime = quality.NeveImage21Runtime()
        attempts = []
        async def run(*args, **kwargs):
            attempts.append(kwargs)
            runtime._adaptive_auxiliary_used = not kwargs['legacy_auxiliary'] and not kwargs['force_gguf']
            if len(attempts) == 1:
                runtime._retry_prompt = 'keep the successful plan'
            else:
                self.assertEqual(runtime._retry_prompt, 'keep the successful plan')
            if len(attempts) <= 2:
                raise RuntimeError('CUDA out of memory')
            return 'recovered'
        with patch.object(runtime, '_run_once', side_effect=run), \
                patch('neveai.routers.stable_diffusion._preferred_sd_cpp_windows_backend', return_value='cuda12'):
            self.assertEqual(await runtime.run('edit', 'auto', ['ref'] * 4, None, AsyncMock()), 'recovered')
        self.assertEqual([(item['force_gguf'], item['legacy_auxiliary']) for item in attempts],
                         [(False, False), (False, True), (True, False)])
        self.assertEqual(len({item['seed'] for item in attempts}), 1)
        self.assertIsNone(runtime._retry_prompt)

    async def test_non_memory_error_never_retries(self):
        runtime = quality.NeveImage21Runtime()
        with patch.object(runtime, '_run_once', AsyncMock(side_effect=ValueError('bad input'))) as run, \
                patch('neveai.routers.stable_diffusion._preferred_sd_cpp_windows_backend', return_value='cuda12'):
            with self.assertRaises(ValueError):
                await runtime.run('edit', 'auto', ['ref'] * 4, None, AsyncMock())
        run.assert_awaited_once()
