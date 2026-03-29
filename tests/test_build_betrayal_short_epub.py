"""Tests for summarized EPUB generation from betrayal_short JSON."""

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import build_betrayal_short_epub


def _write_json(path: Path, data: dict) -> None:
    """Write JSON fixture with UTF-8 encoding for test setup."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def _write_opf(path: Path) -> None:
    """Write minimal OPF file containing a stable dc:identifier."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<package xmlns=\"http://www.idpf.org/2007/opf\" unique-identifier=\"uid\" version=\"3.0\">
  <metadata xmlns:dc=\"http://purl.org/dc/elements/1.1/\">
    <dc:identifier id=\"uid\">urn:uuid:test-book</dc:identifier>
  </metadata>
</package>
""",
        encoding="utf-8",
    )


class BuildBetrayalShortEpubTests(unittest.TestCase):
    """Validate EPUB creation using summarized chapter payloads."""

    def test_build_epub_from_short_json_with_cover(self) -> None:
        """EPUB builder should create file with chapter XHTML and cover asset."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "data" / "betrayal_short.json"
            output_epub = temp_path / "data" / "betrayal_short.epub"
            ops_dir = temp_path / "contents" / "OPS"
            cover_path = ops_dir / "images" / "cover.jpg"
            cover_path.parent.mkdir(parents=True, exist_ok=True)
            cover_path.write_bytes(b"fake-cover-bytes")
            _write_opf(ops_dir / "content.opf")

            _write_json(
                input_json,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": [
                                {
                                    "paragraph_index": 1,
                                    "text": "First summary paragraph.",
                                },
                                {
                                    "paragraph_index": 2,
                                    "text": "Second summary paragraph.",
                                },
                            ],
                        }
                    ],
                },
            )

            build_betrayal_short_epub.build_epub_from_betrayal_short_json(
                json_path=input_json,
                output_path=output_epub,
                ops_dir=ops_dir,
            )

            self.assertTrue(output_epub.exists())
            self.assertGreater(output_epub.stat().st_size, 0)
            with zipfile.ZipFile(output_epub, "r") as archive:
                names = archive.namelist()
                self.assertTrue(any(name.endswith("chap_001.xhtml") for name in names))
                self.assertTrue(any("cover" in name.lower() for name in names))

    def test_rejects_invalid_paragraphs_field(self) -> None:
        """Invalid chapter paragraphs field should fail fast."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "data" / "betrayal_short.json"
            output_epub = temp_path / "data" / "betrayal_short.epub"
            ops_dir = temp_path / "contents" / "OPS"
            cover_path = ops_dir / "images" / "cover.jpg"
            cover_path.parent.mkdir(parents=True, exist_ok=True)
            cover_path.write_bytes(b"fake-cover-bytes")
            _write_opf(ops_dir / "content.opf")

            _write_json(
                input_json,
                {
                    "book_metadata": {
                        "title": "Betrayal",
                        "subtitle": "Power, deceit, and the fight for the future of the Royal family",
                        "author_line": "From the number one bestselling author Tom Bower",
                        "cover": {
                            "source_file": "contents/OPS/001-Cover.xhtml",
                            "image_src": "images/cover.jpg",
                            "image_alt": "cover alt",
                        },
                    },
                    "examples": [
                        {
                            "source_file": "009-Chapter_1.xhtml",
                            "chapter_type": "chapter",
                            "chapter_number": 1,
                            "chapter_label": "CHAPTER 1",
                            "chapter_title": "Manchester",
                            "paragraphs": "invalid",
                        }
                    ],
                },
            )

            with self.assertRaises(ValueError):
                build_betrayal_short_epub.build_epub_from_betrayal_short_json(
                    json_path=input_json,
                    output_path=output_epub,
                    ops_dir=ops_dir,
                )


if __name__ == "__main__":
    unittest.main()
