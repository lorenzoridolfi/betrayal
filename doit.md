# doit Usage

The doit workflow exposes a single task: `pipeline`.

## Full Track (default)

```bash
uv run doit -f ingest/dodo.py pipeline
```

This runs:

- `ingest/pass_01_classify_chapters.py --profile full`
- `ingest/pass_02_extract_and_bundle.py --profile full`

Output file:

- `data/rag_ingest_bundle.json`

## Preview Track (first 2 chapters)

```bash
uv run doit -f ingest/dodo.py pipeline --profile preview
```

This runs:

- `ingest/pass_01_classify_chapters.py --profile preview`
- `ingest/pass_02_extract_and_bundle.py --profile preview`

Output file:

- `data/rag_ingest_bundle_preview.json`

## Direct Script Wrapper

- `uv run python ingest/run_pipeline.py` (default `full`)
- `uv run python ingest/run_pipeline.py preview`
