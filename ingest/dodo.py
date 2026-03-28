from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

DOIT_CONFIG = {
    "dep_file": str(ROOT_DIR / ".doit"),
}


def task_pipeline():
    return {
        "file_dep": [
            "data/betrayal.json",
            "ingest/run_pipeline.py",
            "ingest/pass_01_classify_chapters.py",
            "ingest/pass_02_extract_and_bundle.py",
            "ingest/pipeline_params.py",
            "ingest/pipeline_common.py",
            "prompts/pass_01_classification_system.txt",
            "prompts/pass_02_extraction_system.txt",
            "prompts/pass_01_user.j2",
            "prompts/pass_02_user.j2",
            "schemas/pass_01_chapter_classification.schema.json",
            "schemas/pass_02_rag_bundle.schema.json",
        ],
        "actions": ["uv run python ingest/run_pipeline.py %(profile)s"],
        "params": [
            {
                "name": "profile",
                "long": "profile",
                "default": "full",
                "choices": ["full", "preview"],
            }
        ],
        "clean": True,
    }
