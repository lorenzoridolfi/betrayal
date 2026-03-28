# Two-Pass Ingest Plan (Final)

## Scope

- Stage 0 is complete. Canonical source: `data/betrayal.json`.
- Exactly two passes.
- One program per pass.
- One output file per pass.
- All programs are under `ingest/`.
- All prompts, schemas, and field names are in US English.
- All LLM calls use OpenAI Structured Outputs with strict JSON Schema.

## Required Files

- `ingest/pass_01_classify_chapters.py`
- `ingest/pass_02_extract_and_bundle.py`
- `ingest/pipeline_common.py`
- `schemas/pass_01_chapter_classification.schema.json`
- `schemas/pass_02_rag_bundle.schema.json`
- `ingest/dodo.py`

## Pass 1 (Simple Schema)

### Program

`ingest/pass_01_classify_chapters.py`

### Input

`data/betrayal.json`

### Output (single file)

`data/pass_01_chapter_classification.json`

### Purpose

Classify each chapter and produce a lightweight structured result.

### Required fields per chapter

- `chapter_id`
- `chapter_order`
- `chapter_number` (`integer | null`)
- `chapter_title` (`string | null`)
- `chapter_kind_preliminary` (`narrative | background | analysis | reflection | conclusion | appendix | mixed | other`)
- `classification_confidence` (`low | medium | high`)
- `classification_rationale`
- `dominant_entities` (array of strings)
- `dominant_timeframe` (`string | null`)
- `possible_themes` (array of strings)
- `chapter_summary_preliminary` (one paragraph, plain US English)

### Prompt requirements

- US English only.
- No invented facts.
- Return only strict schema JSON.

### File shape

```json
{
  "book_id": "betrayal",
  "chapters": []
}
```

## Pass 2 (Complete Schema)

### Program

`ingest/pass_02_extract_and_bundle.py`

### Inputs

- `data/betrayal.json`
- `data/pass_01_chapter_classification.json`

### Output (single file)

`data/rag_ingest_bundle.json`

### Purpose

For each chapter, consume the matching preliminary record from Pass 1, then produce final extraction and chunk data in one bundled artifact.

Pass 2 explicitly improves classification quality by confirming or correcting the preliminary label.

### Required content per chapter

- Chapter metadata:
  - `chapter_id`, `chapter_order`, `source_file`, `chapter_type`, `chapter_number`, `chapter_title`
- Final chapter extraction:
  - `chapter_kind`, `chapter_kind_preliminary`, `chapter_kind_changed`, `chapter_kind_change_rationale`, `summary_short`, `summary_detailed`, `summary_confidence`
  - `themes`, `key_events`, `entities`, `time_markers`, `important_quotes`, `open_loops`, `chapter_keywords`, `ambiguities_or_gaps`
- Chunk layer:
  - `chunks[]` with `chunk_id`, `chunk_order`, `source_paragraph_start`, `source_paragraph_end`, `chunk_text_source`, `chunk_text_us_plain`, `chunk_kind`, `entities_mentioned`, `aliases`, `time_markers`, `rewrite_quality`, `fidelity_notes`

### Prompt requirements

- US English only.
- Chunk rewrite must be plain, accessible US English.
- No invented facts.
- Return only strict schema JSON.

### File shape

```json
{
  "book_id": "betrayal",
  "chapters": []
}
```

## OpenAI Call Policy

All LLM calls go through `ingest/pipeline_common.py`.

Required behavior:

- Cache-first lookup before API call.
- Deterministic cache key based on model, prompt, schema name, schema hash, and input hash.
- OpenAI timeout: `240` seconds.
- Tenacity retries for timeout errors and schema-validation errors.
- Save successful responses to cache.
- Validate response JSON against schema before writing pass output files.

## Shared Utilities Policy

All reusable helpers must be centralized in `ingest/pipeline_common.py`, including:

- JSON read/write
- schema loading and validation
- cache read/write and key generation
- OpenAI structured call wrapper
- ID helper functions used across passes

## doit Orchestration

`ingest/dodo.py` controls execution by input/output files.

### Task 1

- Name: `task_pass_01_classify_chapters`
- `file_dep`: `data/betrayal.json`, `ingest/pass_01_classify_chapters.py`, `ingest/pipeline_common.py`, `schemas/pass_01_chapter_classification.schema.json`
- `targets`: `data/pass_01_chapter_classification.json`
- `actions`: `uv run python ingest/pass_01_classify_chapters.py`

### Task 2

- Name: `task_pass_02_extract_and_bundle`
- `file_dep`: `data/betrayal.json`, `data/pass_01_chapter_classification.json`, `ingest/pass_02_extract_and_bundle.py`, `ingest/pipeline_common.py`, `schemas/pass_02_rag_bundle.schema.json`
- `targets`: `data/rag_ingest_bundle.json`
- `actions`: `uv run python ingest/pass_02_extract_and_bundle.py`

## Validation Checklist

- Exactly two passes.
- Exactly one output file per pass.
- Exactly two schemas:
  - `schemas/pass_01_chapter_classification.schema.json` (simple)
  - `schemas/pass_02_rag_bundle.schema.json` (complete)
- Pass 1 includes `chapter_summary_preliminary` (one paragraph).
- Pass 2 consumes Pass 1 per chapter and produces the final bundle.
- All LLM calls use strict OpenAI Structured Outputs.
- Cache + Tenacity + 240-second timeout are required.
- Shared logic is centralized in `ingest/pipeline_common.py`.
- doit uses `file_dep` and `targets` to skip up-to-date tasks.
