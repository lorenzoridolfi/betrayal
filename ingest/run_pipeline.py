"""Run pass 01 and pass 02 sequentially for a selected profile."""

import subprocess
import sys
from pathlib import Path

from pipeline_params import (
    PASS_01_SCRIPT,
    PASS_02_SCRIPT,
    PROFILE_DEFAULT,
    PROFILE_CHOICES,
)


VALID_PROFILES = set(PROFILE_CHOICES)


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
    subprocess.run(command, check=True)


def main() -> None:
    """Run both ingest passes for the resolved profile."""
    try:
        profile = resolve_profile(sys.argv)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error

    run_script(PASS_01_SCRIPT, profile)
    run_script(PASS_02_SCRIPT, profile)


if __name__ == "__main__":
    main()
