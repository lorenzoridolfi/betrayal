def task_pass_01_classify_chapters():
    return {
        "file_dep": [
            "data/betrayal.json",
            "ingest/pass_01_classify_chapters.py",
            "ingest/pipeline_common.py",
            "schemas/pass_01_chapter_classification.schema.json",
        ],
        "targets": ["data/pass_01_chapter_classification.json"],
        "actions": ["uv run python ingest/pass_01_classify_chapters.py"],
        "clean": True,
    }


def task_pass_02_extract_and_bundle():
    return {
        "file_dep": [
            "data/betrayal.json",
            "data/pass_01_chapter_classification.json",
            "ingest/pass_02_extract_and_bundle.py",
            "ingest/pipeline_common.py",
            "schemas/pass_02_rag_bundle.schema.json",
        ],
        "targets": ["data/rag_ingest_bundle.json"],
        "actions": ["uv run python ingest/pass_02_extract_and_bundle.py"],
        "clean": True,
    }
