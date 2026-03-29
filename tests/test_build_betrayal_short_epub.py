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


def _write_short_cover_image(path: Path) -> None:
    """Write short-cover image fixture used by fail-fast cover selection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-short-cover-bytes")


class BuildBetrayalShortEpubTests(unittest.TestCase):
    """Validate EPUB creation using summarized chapter payloads."""

    def test_build_epub_from_short_json_with_cover(self) -> None:
        """EPUB builder should include configured short-cover image asset."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "data" / "betrayal_short.json"
            output_epub = temp_path / "data" / "betrayal_short.epub"
            ops_dir = temp_path / "contents" / "OPS"
            short_cover_path = (
                ops_dir / build_betrayal_short_epub.SHORT_COVER_IMAGE_RELATIVE_PATH
            )
            _write_short_cover_image(short_cover_path)
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
                self.assertTrue(
                    any(
                        name.endswith("images/cover_short_version.png")
                        for name in names
                    )
                )
                self.assertNotIn("EPUB/contents/OPS/001-Cover.xhtml", names)

    def test_rejects_invalid_paragraphs_field(self) -> None:
        """Invalid chapter paragraphs field should fail fast."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "data" / "betrayal_short.json"
            output_epub = temp_path / "data" / "betrayal_short.epub"
            ops_dir = temp_path / "contents" / "OPS"
            short_cover_path = (
                ops_dir / build_betrayal_short_epub.SHORT_COVER_IMAGE_RELATIVE_PATH
            )
            _write_short_cover_image(short_cover_path)
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

    def test_first_chapter_defaults_to_prologue_when_title_missing(self) -> None:
        """First chapter with missing title should be rendered as Prologue."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "data" / "betrayal_short.json"
            output_epub = temp_path / "data" / "betrayal_short.epub"
            ops_dir = temp_path / "contents" / "OPS"
            short_cover_path = (
                ops_dir / build_betrayal_short_epub.SHORT_COVER_IMAGE_RELATIVE_PATH
            )
            _write_short_cover_image(short_cover_path)
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
                            "source_file": "008-Prologue.xhtml",
                            "chapter_type": "prologue",
                            "chapter_number": None,
                            "chapter_label": None,
                            "chapter_title": None,
                            "paragraphs": [
                                {
                                    "paragraph_index": 1,
                                    "text": "Intro paragraph.",
                                }
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

            with zipfile.ZipFile(output_epub, "r") as archive:
                chapter_xhtml = archive.read("EPUB/chap_001.xhtml").decode("utf-8")
                self.assertIn("<h1>Prologue</h1>", chapter_xhtml)

    def test_rejects_missing_short_cover_image(self) -> None:
        """Missing short-cover image should fail fast with FileNotFoundError."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_json = temp_path / "data" / "betrayal_short.json"
            output_epub = temp_path / "data" / "betrayal_short.epub"
            ops_dir = temp_path / "contents" / "OPS"
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
                                }
                            ],
                        }
                    ],
                },
            )

            with self.assertRaises(FileNotFoundError):
                build_betrayal_short_epub.build_epub_from_betrayal_short_json(
                    json_path=input_json,
                    output_path=output_epub,
                    ops_dir=ops_dir,
                )


if __name__ == "__main__":
    unittest.main()
