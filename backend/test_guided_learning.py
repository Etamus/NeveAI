import copy
import unittest
from neveai.utils.guided_learning import apply_guided_learning, GUIDED_LEARNING_PROMPT


class GuidedLearningTests(unittest.TestCase):
    def test_inactive_is_unchanged(self):
        messages = [{'role': 'user', 'content': 'Hello'}]
        self.assertIs(apply_guided_learning(messages, {}), messages)
        self.assertIs(apply_guided_learning(messages, {'guided_learning': False}), messages)

    def test_preserves_system_and_multimodal_material(self):
        messages = [{'role': 'system', 'content': 'Existing requirement'},
                    {'role': 'user', 'content': [{'type': 'text', 'text': 'Teach me'},
                                               {'type': 'image_url', 'image_url': {'url': 'test'}}]}]
        original = copy.deepcopy(messages)
        result = apply_guided_learning(messages, {'guided_learning': True})
        self.assertEqual(messages, original)
        self.assertIn('Existing requirement', result[0]['content'])
        self.assertIn(GUIDED_LEARNING_PROMPT, result[0]['content'])
        self.assertEqual(result[1], messages[1])

    def test_media_and_generated_document_are_not_modified(self):
        messages = [{'role': 'user', 'content': 'Create something'}]
        for key in ('stable_diffusion', 'video_generation', 'music_generation'):
            self.assertIs(apply_guided_learning(messages, {'guided_learning': True, key: True}), messages)
        self.assertIs(apply_guided_learning(messages, {'guided_learning': True}, generated_file_ready=True), messages)

    def test_tutoring_has_no_extra_turn_or_persistent_message(self):
        messages = [{'role': 'user', 'content': 'Explain fractions'}]
        for _ in range(3):
            result = apply_guided_learning(messages, {'guided_learning': True})
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]['content'].count('Guided learning is enabled'), 1)
        self.assertEqual(len(messages), 1)


if __name__ == '__main__':
    unittest.main()
