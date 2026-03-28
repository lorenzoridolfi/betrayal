"""Run pass 01, pass 1.5, and pass 02 for a selected profile."""

import subprocess
import sys
from pathlib import Path

from logging_utils import configure_logging, get_logger
from pipeline_params import (
    PASS_01_SCRIPT,
    PASS_01_5_SCRIPT,
    PASS_02_SCRIPT,
    PROFILE_DEFAULT,
    PROFILE_CHOICES,
)


VALID_PROFILES = set(PROFILE_CHOICES)
logger = get_logger(__name__)


def resolve_profile(argv: list[str]) -> str:
    """Parse the optional profile arg and fail fast on invalid values."""
    if len(argv) <= 1:
        return PROFILE_DEFAULT
    profile = argv[1].strip().lower()
    if profile not in VALID_PROFILES:
        allowed = " or ".join(f"'{name}'" for name in PROFILE_CHOICES)
        raise ValueError(f"Profile must be {allowed}.")
    return profile


def run_script(script_path: Path, profile: str) -> None:
    """Execute one ingest script with the selected profile."""
    command = [sys.executable, str(script_path), "--profile", profile]
    logger.info("Running script=%s profile=%s", script_path.name, profile)
    subprocess.run(command, check=True)


def main() -> None:
    """Run all ingest passes for the resolved profile."""
    effective_log_level = configure_logging()
    logger.debug("Starting run_pipeline with LOG_LEVEL=%s", effective_log_level)

    try:
        profile = resolve_profile(sys.argv)
    except ValueError as error:
        logger.error("%s", str(error))
        raise SystemExit(2) from error

    logger.info("Running ingest pipeline profile=%s", profile)
    run_script(PASS_01_SCRIPT, profile)
    run_script(PASS_01_5_SCRIPT, profile)
    run_script(PASS_02_SCRIPT, profile)
    logger.info("Ingest pipeline completed profile=%s", profile)


if __name__ == "__main__":
    main()
