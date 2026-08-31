import unittest
import io

from file_readers import FileProcessingError, process_upload


class FileReaderTests(unittest.TestCase):
    def test_source_code_is_extracted_with_language_metadata(self):
        item = process_upload("sample.py", "text/x-python", b"print('hello')\n")
        self.assertEqual(item.category, "code")
        self.assertEqual(item.metadata["language"], "Python")
        self.assertIn("print('hello')", item.extracted_text)
        self.assertEqual(item.size, len(b"print('hello')\n"))
        self.assertEqual(len(item.sha256), 64)

    def test_utf8_text_document_is_read(self):
        item = process_upload("notes.txt", "text/plain", "Résumé\nsecond line".encode())
        self.assertEqual(item.category, "text")
        self.assertIn("Résumé", item.extracted_text)
        self.assertEqual(item.metadata["line_count"], 2)

    def test_unknown_binary_is_kept_as_an_attachment(self):
        item = process_upload("archive.bin", "application/octet-stream", b"\x00\xff\x10")
        self.assertEqual(item.category, "file")
        self.assertTrue(item.sha256)
        self.assertIn("file type has no text extractor", item.extracted_text)

    def test_invalid_pdf_returns_a_readable_error(self):
        with self.assertRaises(FileProcessingError):
            process_upload("bad.pdf", "application/pdf", b"not a pdf")

    def test_docx_paragraphs_are_extracted(self):
        from docx import Document

        buffer = io.BytesIO()
        document = Document()
        document.add_paragraph("A document paragraph")
        document.save(buffer)
        item = process_upload("notes.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buffer.getvalue())
        self.assertEqual(item.category, "document")
        self.assertIn("A document paragraph", item.extracted_text)
        self.assertEqual(item.metadata["paragraph_count"], 1)

    def test_image_is_prepared_for_vision_and_original_is_hashed(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (24, 12), color=(40, 120, 60)).save(buffer, format="PNG")
        original = buffer.getvalue()
        item = process_upload("green.png", "image/png", original)
        self.assertEqual(item.category, "image")
        self.assertEqual(item.metadata["width"], 24)
        self.assertEqual(item.metadata["height"], 12)
        self.assertTrue(item.model_images)
        self.assertEqual(item.size, len(original))


if __name__ == "__main__":
    unittest.main()
