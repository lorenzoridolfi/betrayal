from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
SCHEMAS_DIR = ROOT_DIR / "schemas"
PROMPTS_DIR = ROOT_DIR / "prompts"

MODEL_DEFAULT = "gpt-5-mini"
TIMEOUT_SECONDS_DEFAULT = 240

BOOK_FILE = DATA_DIR / "betrayal.json"

PASS_01_OUTPUT_FULL = DATA_DIR / "pass_01_chapter_classification.json"
PASS_01_OUTPUT_PREVIEW = DATA_DIR / "pass_01_chapter_classification_preview.json"

PASS_02_OUTPUT_FULL = DATA_DIR / "rag_ingest_bundle.json"
PASS_02_OUTPUT_PREVIEW = DATA_DIR / "rag_ingest_bundle_preview.json"

PASS_01_SCHEMA_FILE = SCHEMAS_DIR / "pass_01_chapter_classification.schema.json"
PASS_02_SCHEMA_FILE = SCHEMAS_DIR / "pass_02_rag_bundle.schema.json"

PASS_01_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "pass_01_classification_system.txt"
PASS_02_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "pass_02_extraction_system.txt"
PASS_01_USER_PROMPT_TEMPLATE_FILE = PROMPTS_DIR / "pass_01_user.j2"
PASS_02_USER_PROMPT_TEMPLATE_FILE = PROMPTS_DIR / "pass_02_user.j2"


def list_profiles() -> tuple[str, ...]:
    return ("full", "preview")


def get_profile(profile: str) -> dict:
    if profile == "full":
        return {
            "book_file": BOOK_FILE,
            "pass_01_output": PASS_01_OUTPUT_FULL,
            "pass_02_output": PASS_02_OUTPUT_FULL,
            "chapter_limit": None,
        }
    if profile == "preview":
        return {
            "book_file": BOOK_FILE,
            "pass_01_output": PASS_01_OUTPUT_PREVIEW,
            "pass_02_output": PASS_02_OUTPUT_PREVIEW,
            "chapter_limit": 2,
        }
    raise ValueError(f"Unknown profile: {profile}")
