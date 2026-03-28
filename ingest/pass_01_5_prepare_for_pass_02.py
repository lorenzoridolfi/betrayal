"""Pass 1.5: copy validated pass-01 output for pass-02 consumption."""

import argparse
from pathlib import Path

from logging_utils import configure_logging, get_logger
from pipeline_common import load_schema, read_json, validate_with_schema, write_json
from pipeline_params import (
    PASS_01_OUTPUT_FULL,
    PASS_01_OUTPUT_PREVIEW,
    PASS_01_5_OUTPUT_FULL,
    PASS_01_5_OUTPUT_PREVIEW,
    PASS_01_SCHEMA_FILE,
    PROFILE_DEFAULT,
    PROFILE_FULL,
    PROFILE_PREVIEW,
    list_profiles,
)


logger = get_logger(__name__)


def _default_input_for_profile(profile: str) -> Path:
    """Return default pass-01 input file for the selected profile."""
    if profile == PROFILE_PREVIEW:
        return PASS_01_OUTPUT_PREVIEW
    if profile == PROFILE_FULL:
        return PASS_01_OUTPUT_FULL
    raise ValueError(f"Unsupported profile: {profile}")


def _default_output_for_profile(profile: str) -> Path:
    """Return default pass-1.5 output file for the selected profile."""
    if profile == PROFILE_PREVIEW:
        return PASS_01_5_OUTPUT_PREVIEW
    if profile == PROFILE_FULL:
        return PASS_01_5_OUTPUT_FULL
    raise ValueError(f"Unsupported profile: {profile}")


def main() -> None:
    """Validate pass-01 output and write an equivalent pass-1.5 artifact."""
    effective_log_level = configure_logging()
    logger.debug("Starting pass_01_5 with LOG_LEVEL=%s", effective_log_level)

    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=list_profiles(), default=PROFILE_DEFAULT)
    parser.add_argument("--input-file", default=None)
    parser.add_argument("--output-file", default=None)
    args = parser.parse_args()

    input_file = (
        Path(args.input_file)
        if args.input_file
        else _default_input_for_profile(args.profile)
    )
    output_file = (
        Path(args.output_file)
        if args.output_file
        else _default_output_for_profile(args.profile)
    )
    logger.info(
        "pass_01_5 profile=%s input=%s output=%s",
        args.profile,
        input_file,
        output_file,
    )

    schema = load_schema(PASS_01_SCHEMA_FILE)
    input_data = read_json(input_file)
    validate_with_schema(input_data, schema)

    output_data = {
        "book_id": input_data["book_id"],
        "chapters": list(input_data["chapters"]),
    }
    validate_with_schema(output_data, schema)
    write_json(output_file, output_data)
    logger.info(
        "pass_01_5 wrote %s with %d chapters",
        output_file.name,
        len(output_data["chapters"]),
    )


if __name__ == "__main__":
    main()
