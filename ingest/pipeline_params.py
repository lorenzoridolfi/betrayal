"""Centralized constants and profile settings for the ingest pipeline."""

from project_paths import DATA_DIR, INGEST_DIR, PROMPTS_DIR, ROOT_DIR, SCHEMAS_DIR


PROFILE_FULL = "full"
PROFILE_PREVIEW = "preview"
PROFILE_CHOICES = (PROFILE_FULL, PROFILE_PREVIEW)
PROFILE_DEFAULT = PROFILE_FULL
BOOK_ID = "betrayal"

MODEL_DEFAULT = "gpt-5-mini"
TIMEOUT_SECONDS_DEFAULT = 240
PASS_02_SCHEMA_VERSION = "2.2.0"
PASS_02_PIPELINE_VERSION = "pass_02_v1_2"
DOTENV_MASTER_KEY_PATH_DEFAULT = "/Users/lorenzo/Sync/Tech/Keys/openai.key"
DOTENV_ENC_PATH_DEFAULT = ".env.enc"
OPENAI_ALLOW_PLAINTEXT_DOTENV_FALLBACK_DEFAULT = False

BOOK_FILE = DATA_DIR / "betrayal.json"
SCHEMA_CONTRACT_VALIDATION_FILE = DATA_DIR / "schema_contract_validation.json"

PASS_01_OUTPUT_FULL = DATA_DIR / "pass_01_chapter_classification.json"
PASS_01_OUTPUT_PREVIEW = DATA_DIR / "pass_01_chapter_classification_preview.json"
PASS_01_5_OUTPUT_FULL = DATA_DIR / "pass_01_5_chapter_classification.json"
PASS_01_5_OUTPUT_PREVIEW = DATA_DIR / "pass_01_5_chapter_classification_preview.json"

PASS_02_OUTPUT_FULL = DATA_DIR / "rag_ingest_bundle.json"
PASS_02_OUTPUT_PREVIEW = DATA_DIR / "rag_ingest_bundle_preview.json"

PASS_01_SCHEMA_FILE = SCHEMAS_DIR / "pass_01_chapter_classification.schema.json"
PASS_02_SCHEMA_FILE = SCHEMAS_DIR / "pass_02_rag_bundle.schema.json"
PASS_01_ITEM_SCHEMA_FILE = (
    SCHEMAS_DIR / "pass_01_chapter_classification_item.schema.json"
)
PASS_02_ITEM_SCHEMA_FILE = SCHEMAS_DIR / "pass_02_rag_bundle_item.schema.json"

PASS_01_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "pass_01_classification_system.txt"
PASS_02_SYSTEM_PROMPT_FILE = PROMPTS_DIR / "pass_02_extraction_system.txt"
PASS_01_USER_PROMPT_TEMPLATE_FILE = PROMPTS_DIR / "pass_01_user.j2"
PASS_02_USER_PROMPT_TEMPLATE_FILE = PROMPTS_DIR / "pass_02_user.j2"

RUN_PIPELINE_SCRIPT = INGEST_DIR / "run_pipeline.py"
PASS_01_SCRIPT = INGEST_DIR / "pass_01_classify_chapters.py"
PASS_01_5_SCRIPT = INGEST_DIR / "pass_01_5_prepare_for_pass_02.py"
PASS_02_SCRIPT = INGEST_DIR / "pass_02_extract_and_bundle.py"
PIPELINE_COMMON_FILE = INGEST_DIR / "pipeline_common.py"
PIPELINE_PARAMS_FILE = INGEST_DIR / "pipeline_params.py"
VALIDATE_SCHEMA_CONTRACTS_SCRIPT = INGEST_DIR / "validate_schema_contracts.py"


SCHEMA_CONTRACT_FILE_DEPS = [
    VALIDATE_SCHEMA_CONTRACTS_SCRIPT,
    PIPELINE_PARAMS_FILE,
    PIPELINE_COMMON_FILE,
    PASS_01_SCHEMA_FILE,
    PASS_01_ITEM_SCHEMA_FILE,
    PASS_02_SCHEMA_FILE,
    PASS_02_ITEM_SCHEMA_FILE,
]


PIPELINE_FILE_DEPS = [
    BOOK_FILE,
    RUN_PIPELINE_SCRIPT,
    PASS_01_SCRIPT,
    PASS_01_5_SCRIPT,
    PASS_02_SCRIPT,
    PIPELINE_PARAMS_FILE,
    PIPELINE_COMMON_FILE,
    PASS_01_SYSTEM_PROMPT_FILE,
    PASS_02_SYSTEM_PROMPT_FILE,
    PASS_01_USER_PROMPT_TEMPLATE_FILE,
    PASS_02_USER_PROMPT_TEMPLATE_FILE,
    PASS_01_SCHEMA_FILE,
    PASS_01_ITEM_SCHEMA_FILE,
    PASS_02_SCHEMA_FILE,
    PASS_02_ITEM_SCHEMA_FILE,
]


def list_profiles() -> tuple[str, ...]:
    """Return the accepted execution profiles."""
    return PROFILE_CHOICES


def get_profile(profile: str) -> dict:
    """Resolve a profile into its input, output, and chapter-limit settings."""
    if profile == PROFILE_FULL:
        return {
            "book_file": BOOK_FILE,
            "pass_01_output": PASS_01_OUTPUT_FULL,
            "pass_01_5_output": PASS_01_5_OUTPUT_FULL,
            "pass_02_output": PASS_02_OUTPUT_FULL,
            "chapter_limit": None,
        }
    if profile == PROFILE_PREVIEW:
        return {
            "book_file": BOOK_FILE,
            "pass_01_output": PASS_01_OUTPUT_PREVIEW,
            "pass_01_5_output": PASS_01_5_OUTPUT_PREVIEW,
            "pass_02_output": PASS_02_OUTPUT_PREVIEW,
            "chapter_limit": 2,
        }
    raise ValueError(f"Unknown profile: {profile}")
