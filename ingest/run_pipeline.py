import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
PASS_01_SCRIPT = ROOT_DIR / "ingest" / "pass_01_classify_chapters.py"
PASS_02_SCRIPT = ROOT_DIR / "ingest" / "pass_02_extract_and_bundle.py"
VALID_PROFILES = {"full", "preview"}


def resolve_profile(argv: list[str]) -> str:
    if len(argv) <= 1:
        return "full"
    profile = argv[1].strip().lower()
    if profile not in VALID_PROFILES:
        raise ValueError("Profile must be 'full' or 'preview'.")
    return profile


def run_script(script_path: Path, profile: str) -> None:
    command = [sys.executable, str(script_path), "--profile", profile]
    subprocess.run(command, check=True)


def main() -> None:
    try:
        profile = resolve_profile(sys.argv)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error

    run_script(PASS_01_SCRIPT, profile)
    run_script(PASS_02_SCRIPT, profile)


if __name__ == "__main__":
    main()
