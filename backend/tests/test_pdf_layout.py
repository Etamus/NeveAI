import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from neveai.retrieval.pdf_layout import has_fragmented_pdf_text, repair_pdf_content, read_pdf_layout


class PDFLayoutTests(unittest.TestCase):
    def tearDown(self):
        read_pdf_layout.cache_clear()

    def test_normal_paragraphs_and_short_lists_are_unchanged(self):
        for text in ['First paragraph with several words.\nSecond paragraph.', 'one\ntwo\nthree']:
            self.assertFalse(has_fragmented_pdf_text(text))
            self.assertEqual(repair_pdf_content('missing.pdf', text), text)

    def test_fragmented_content_is_recovered_once_and_cache_tracks_file_changes(self):
        text = '\n \n'.join(['word'] * 100)
        self.assertTrue(has_fragmented_pdf_text(text))
        page = type('Page', (), {'extract_text': lambda self, **kwargs: 'Restored paragraph with readable lines.'})()
        reader = type('Reader', (), {'pages': [page]})()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.pdf'
            path.write_bytes(b'fixture')
            with patch('pypdf.PdfReader', return_value=reader) as read:
                self.assertEqual(repair_pdf_content(str(path), text), 'Restored paragraph with readable lines.')
                repair_pdf_content(str(path), text)
                self.assertEqual(read.call_count, 1)
                path.write_bytes(b'changed fixture')
                repair_pdf_content(str(path), text)
                self.assertEqual(read.call_count, 2)

    def test_missing_or_invalid_pdf_retains_original_content(self):
        text = '\n'.join(['word'] * 100)
        self.assertEqual(repair_pdf_content('missing.pdf', text), text)


if __name__ == '__main__':
    unittest.main()
