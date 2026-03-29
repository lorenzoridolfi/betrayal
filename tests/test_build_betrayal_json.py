"""Tests for cover metadata extraction in build_betrayal_json.py."""

import unittest

import build_betrayal_json


class BuildBetrayalJsonTests(unittest.TestCase):
    """Validate cover metadata parsing from the original cover XHTML file."""

    def test_parse_cover_metadata_from_original_cover_file(self) -> None:
        """Cover parser should extract required minimal metadata fields."""
        metadata = build_betrayal_json.parse_cover_metadata(
            build_betrayal_json.BOOK_COVER_FILE
        )

        self.assertEqual(metadata["title"], "Betrayal")
        self.assertEqual(
            metadata["subtitle"],
            "Power, deceit, and the fight for the future of the Royal family",
        )
        self.assertEqual(
            metadata["author_line"],
            "From the number one bestselling author Tom Bower",
        )
        self.assertEqual(
            metadata["cover"]["source_file"], "contents/OPS/001-Cover.xhtml"
        )
        self.assertEqual(metadata["cover"]["image_src"], "images/cover.jpg")
        self.assertTrue(metadata["cover"]["image_alt"])


if __name__ == "__main__":
    unittest.main()
