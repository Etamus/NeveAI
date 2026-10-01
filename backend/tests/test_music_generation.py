import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from neveai.routers.music_generation import (
    _build_music_generation_request,
    infer_music_audio_plan,
)
from neveai.utils.middleware import (
    _collect_music_audio_attachments,
    _ensure_requested_music_phrases,
    _get_current_music_files,
    _split_music_request,
)


class MusicGenerationTests(unittest.TestCase):
    def setUp(self):
        self.music_plan = {
            "caption": "Brazilian alternative rock, female vocals",
            "lyrics": "[Verso]\nUma letra em portugues",
            "instrumental": False,
        }

    def test_plain_generation_uses_music_lm_without_rewriting_inputs(self):
        request = _build_music_generation_request(
            "Crie uma musica de rock",
            self.music_plan,
            lm_model="acestep-5Hz-lm-1.7B",
        )
        self.assertTrue(request["thinking"])
        self.assertFalse(request["use_cot_caption"])
        self.assertFalse(request["use_cot_language"])
        self.assertEqual(request["vocal_language"], "pt")
        self.assertEqual(request["lyrics"], self.music_plan["lyrics"])

    def test_reference_audio_keeps_text_to_music_pipeline(self):
        plan = infer_music_audio_plan(
            "Use este audio como referencia para a voz e crie uma musica nova", 1
        )
        self.assertEqual(plan["task_type"], "text2music")
        self.assertTrue(plan["uses_reference_audio"])

    def test_attached_audio_defaults_to_cover(self):
        plan = infer_music_audio_plan("Transforme esta musica em rock", 1)
        request = _build_music_generation_request(
            "Transforme esta musica em rock",
            self.music_plan,
            audio_plan=plan,
            lm_model="acestep-5Hz-lm-1.7B",
        )
        self.assertEqual(request["task_type"], "cover")
        self.assertFalse(request["thinking"])
        self.assertNotIn("audio_duration", request)

    def test_preservation_request_uses_strong_cover(self):
        plan = infer_music_audio_plan(
            'Matenha a letra dessa musica, mas coloque algum trecho com o nome "Mateus"', 1
        )
        self.assertEqual(plan["task_type"], "cover")
        self.assertEqual(plan["audio_cover_strength"], 1.0)
        self.assertEqual(plan["cover_noise_strength"], 0.75)

    def test_full_lyrics_replacement_allows_new_vocal_performance(self):
        plan = infer_music_audio_plan(
            "Troque a letra inteira da musica por essa:", 1
        )

        self.assertEqual(plan["task_type"], "cover")
        self.assertEqual(plan["audio_cover_strength"], 1.0)
        self.assertEqual(plan["cover_noise_strength"], 0.4)
        self.assertTrue(plan["preserve_source"])
        self.assertTrue(plan["replace_entire_lyrics"])

    def test_full_lyrics_replacement_extracts_user_text_verbatim(self):
        prompt = (
            "Troque a letra inteira da música por essa:\n\n"
            "É que é meio complicado\nTenho as tuas memórias"
        )

        style_request, lyrics = _split_music_request(prompt)

        self.assertEqual(style_request, "Crie uma música fiel ao estilo solicitado.")
        self.assertEqual(
            lyrics, "É que é meio complicado\nTenho as tuas memórias"
        )

    def test_requested_name_is_guaranteed_in_edited_lyrics(self):
        lyrics = _ensure_requested_music_phrases(
            'Mantenha a letra, mas coloque algum trecho com o nome "Mateus"',
            "[Verso]\nUma letra que ainda nao tem o nome",
        )
        self.assertIn("Mateus", lyrics)

    def test_repaint_parses_portuguese_time_range(self):
        plan = infer_music_audio_plan(
            "Refaca apenas o trecho de 00:12 a 00:27 e preserve o restante", 1
        )
        self.assertEqual(plan["task_type"], "repaint")
        self.assertEqual(plan["chunk_mask_mode"], "explicit")
        self.assertEqual(plan["repainting_start"], 12.0)
        self.assertEqual(plan["repainting_end"], 27.0)

    def test_untimed_section_edit_uses_preserving_cover(self):
        plan = infer_music_audio_plan("Melhore o refrao deste trecho", 1)
        self.assertEqual(plan["task_type"], "cover")

    def test_time_range_alone_selects_repaint(self):
        plan = infer_music_audio_plan("Mude de 10 segundos ate 25 segundos", 1)
        self.assertEqual(plan["task_type"], "repaint")
        self.assertEqual(plan["repainting_start"], 10.0)
        self.assertEqual(plan["repainting_end"], 25.0)

    def test_repeated_audio_entry_counts_as_one_attachment(self):
        with TemporaryDirectory() as directory:
            audio_path = Path(directory) / "reference.wav"
            audio_path.touch()
            file_object = SimpleNamespace(path=str(audio_path))
            repeated_item = {
                "id": "audio-1",
                "name": "reference.wav",
                "content_type": "audio/wav",
            }
            form_data = {"files": [repeated_item, repeated_item, repeated_item]}

            with (
                patch(
                    "neveai.utils.middleware.Files.get_file_by_id_and_user_id",
                    return_value=file_object,
                ),
                patch(
                    "neveai.utils.middleware.Storage.get_file",
                    return_value=str(audio_path),
                ),
            ):
                attachments = _collect_music_audio_attachments(
                    form_data, SimpleNamespace(id="user-1")
                )

        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0]["path"], str(audio_path))

    def test_music_uses_only_files_from_current_turn(self):
        old_audio = {"id": "old-audio", "name": "old.mp3", "type": "audio"}
        current_audio = {
            "id": "current-audio",
            "name": "current.mp3",
            "type": "audio",
        }
        form_data = {
            "files": [old_audio, current_audio],
            "messages": [
                {"role": "user", "content": "Pedido anterior", "files": [old_audio]},
                {"role": "user", "content": "Pedido atual", "files": [current_audio]},
            ],
        }

        selected = _get_current_music_files(
            form_data, {"__music_current_turn_files__": [current_audio]}
        )

        self.assertEqual(selected, [current_audio])

    def test_music_does_not_reuse_previous_audio_without_new_attachment(self):
        old_audio = {"id": "old-audio", "name": "old.mp3", "type": "audio"}
        form_data = {
            "files": [old_audio],
            "messages": [
                {"role": "user", "content": "Pedido anterior", "files": [old_audio]},
                {"role": "user", "content": "Pedido atual"},
            ],
        }

        selected = _get_current_music_files(
            form_data, {"__music_current_turn_files__": []}
        )

        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main()
