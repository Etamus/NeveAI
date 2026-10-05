import unittest

from neveai.routers.llamacpp import (
    _LoadedModelInfo,
    _speculative_decoding_args,
    _token_prediction_args,
)


class LlamaCppAccelerationTests(unittest.TestCase):
    def test_legacy_low_migrates_to_high(self):
        self.assertEqual(
            _speculative_decoding_args("low"),
            [
                "--spec-type", "ngram-mod",
                "--spec-ngram-mod-n-match", "16",
                "--spec-ngram-mod-n-min", "8",
                "--spec-ngram-mod-n-max", "32",
            ],
        )

    def test_high_uses_longer_but_bounded_ngram_drafts(self):
        self.assertEqual(
            _speculative_decoding_args("high"),
            [
                "--spec-type", "ngram-mod",
                "--spec-ngram-mod-n-match", "16",
                "--spec-ngram-mod-n-min", "8",
                "--spec-ngram-mod-n-max", "32",
            ],
        )

    def test_mtp_uses_the_calibrated_limit_for_current_and_legacy_preferences(self):
        for mode in ("on", "stable", "aggressive", " ON "):
            with self.subTest(mode=mode):
                self.assertEqual(
                    _token_prediction_args(mode),
                    ["--spec-type", "draft-mtp", "--spec-draft-n-max", "4"],
                )

    def test_off_and_default_never_implicitly_enable_acceleration(self):
        for mode in (None, "", "off", "default", "unknown"):
            with self.subTest(mode=mode):
                self.assertEqual(_speculative_decoding_args(mode), [])
                self.assertEqual(_token_prediction_args(mode), [])

    def test_mode_normalization_is_preserved(self):
        self.assertEqual(_speculative_decoding_args(" HIGH "), _speculative_decoding_args("high"))

    def test_mtp_and_ngrams_remain_mutually_exclusive(self):
        model = _LoadedModelInfo(
            "local/test", "test.gguf", 99, 8192, 1,
            speculative_decoding="high", token_prediction="on",
        )
        self.assertEqual(model.token_prediction, "on")
        self.assertEqual(model.speculative_decoding, "off")

    def test_context_shift_still_disables_both_acceleration_modes(self):
        model = _LoadedModelInfo(
            "local/test", "test.gguf", 99, 8192, 1,
            speculative_decoding="high", token_prediction="on", context_shift="on",
        )
        self.assertEqual(model.context_shift, "on")
        self.assertEqual(model.token_prediction, "off")
        self.assertEqual(model.speculative_decoding, "off")


if __name__ == "__main__":
    unittest.main()
