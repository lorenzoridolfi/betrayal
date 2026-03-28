# JSON Schema Design for RAG Pipelines: Vector Through Graph

**Structuring chunk metadata, entity annotations, and graph edges for a biography book demands a schema that serves two masters—vector similarity and graph traversal—while guiding LLM extraction with surgical precision.** The best schemas emerging from 2024–2025 practice treat JSON Schema `description` fields as extraction instructions (not documentation), use hierarchical chunk relationships with named vectors for multi-perspective retrieval, and model entities/relationships as first-class objects with temporal bounds and provenance from day one. This report synthesizes field-level recommendations from Microsoft GraphRAG, Weaviate, LlamaIndex, Neo4j, and recent academic research into a unified design framework for a ~120k-token biography across 46 chapters.

---

## Phase 1: The anatomy of a vector-ready chunk schema

A chunk destined for FAISS or Weaviate needs three categories of fields: **identification and positioning**, **content and embeddings**, and **retrieval-enhancing metadata**. The most critical design choice is what text gets embedded versus what gets indexed for keyword search—these are rarely the same.

**Core identification** requires a deterministic `chunk_id` (composite key like `bio-ch03-chunk-0042` or a UUID5 hash of `doc_id + chapter + sequence`), `chapter_number`, `chapter_title`, `chunk_index`, `global_position`, `start_char_idx`, `end_char_idx`, and `token_count`. LlamaIndex's `TextNode` natively tracks character offsets for precise citation. For a 46-chapter biography, chapter-level filtering is essential—Weaviate's starter guide explicitly demonstrates storing `chapter_title` and `chunk_index` per chunk for filtered retrieval.

**Content fields** should include raw `text` (returned to users), `text_cleaned` (normalized for embedding), an LLM-generated `summary`, a descriptive `title`, and `questions_answerable`—hypothetical questions the chunk can answer. Microsoft's RAG enrichment guide specifically recommends this last field because question-to-question vector matching often outperforms query-to-passage matching. The `summary` field also serves double duty: embedded separately via named vectors, it enables thematic search that raw content embeddings miss.

**Embedding strategy** is where modern practice has shifted dramatically. Rather than a single embedding per chunk, the recommended approach uses **multiple named vectors**. Weaviate's named vectors feature stores separate embeddings for content, summary, and entity context on the same object, each queryable independently. For FAISS, this means maintaining parallel indices with shared docstore IDs. The concatenation strategy matters too: prepend chapter title and section header to chunk text before embedding. LlamaIndex's `metadata_template` supports this natively. For biography narrative specifically, Jina AI's late chunking technique (2024) processes the full document through the transformer first, then splits—preserving cross-chunk pronoun references like "he" that refer to the subject from earlier text.

### Hybrid search demands separate keyword-optimized fields

Hybrid search (dense + sparse) yields **15–30% better recall** than either method alone. The schema must explicitly separate fields optimized for BM25 from those optimized for vector similarity. Store `keywords` (extracted via KeyBERT or RAKE), typed `entity_names` as `TEXT_ARRAY`, `themes`, and a dedicated `bm25_boost_text` field concatenating chapter title, section header, and extracted keywords. This boost field should be excluded from vectorization entirely—in Weaviate, set `skip_vectorization=True`; in LlamaIndex, use `excluded_embed_metadata_keys`.

Entity annotations within chunks should include both a flat `entity_ids` array (for fast filtering) and a detailed `entities` array with `entity_id`, `canonical_name`, `mention_text`, `entity_type`, `start_char`, `end_char`, and `confidence`. The flat array enables Weaviate filtering; the detailed array enables precise citation. For on-the-fly entity tagging during ingestion, GLiNER (a BERT-based generalized NER model) is recommended by Weaviate's advanced RAG guide.

### Chunk relationships require a hierarchy plus sequential links

The dominant pattern from LlamaIndex and LangChain is a **three-tier hierarchy** for narrative content. Chapter-level chunks (46 total) hold full chapter text and summaries. Section/passage-level chunks (200–500 total, **512–1024 tokens with 10–20% overlap**) serve as primary retrieval targets. Sentence-level chunks enable fine-grained matching. LlamaIndex's `AutoMergingRetriever` automatically replaces retrieved leaf nodes with their parent when a majority of siblings are retrieved—ideal for biography narrative where context preservation matters.

Sequential links (`previous`/`next` chunk IDs) follow LlamaIndex's `NodeRelationship` enum pattern. Cross-references for narrative callbacks (e.g., a childhood event referenced in a later chapter) should store `target_chunk_id`, `relationship_type`, `description`, and `confidence`. For overlap tracking, store `overlap_tokens_prev`, `overlap_tokens_next`, and `shared_text_hash` for each overlap region—enabling both hash-based and position-based deduplication at retrieval time.

---

## Weaviate-specific schema patterns that matter

Weaviate's collection architecture offers several features that fundamentally shape schema design for RAG. Understanding these avoids common pitfalls.

**Collection structure**: For the biography use case, three collections work well—`BiographyChunk` (primary retrieval target), `Entity` (deduplicated people, orgs, places), and `Event` (timeline events with dates and participants). Weaviate warns that each collection adds indexing and storage overhead, so 3–5 collections is the sweet spot. An alternative single-collection approach with a `node_type` discriminator property works for simpler deployments but loses schema precision.

**Named vectors** (the `Configure.Vectors` API, replacing deprecated `Configure.NamedVectors` as of client v4.16.0) should define at minimum: `content_vector` from the `content` property, `summary_vector` from the `summary` property, and `entity_context_vector` from `entity_names` + `themes` + `time_period`. Each vector can use a different model and has its own HNSW index. Queries must specify `target_vector` to select which embedding space to search. This multi-vector approach dramatically improves retrieval precision—a thematic query like "themes of resilience" routes to the summary vector, while "what happened in Chicago in 1923" routes to the content vector.

**Cross-references vs. denormalization** is the most consequential Weaviate design decision. Cross-references enable graph-like traversal between collections (chunk→entity, entity→entity), but Weaviate's documentation explicitly warns that **cross-reference queries can be significantly slower at scale**. The recommended hybrid approach: denormalize frequently-filtered metadata (entity names, themes as `TEXT_ARRAY` properties) directly onto chunks for fast filtered search, and reserve cross-references for rich relational traversal where you need full entity profiles or narrative flow links. At the ~120k-token biography scale, cross-reference performance is manageable—the warning applies more to millions of objects.

**Tokenization configuration** is critical for hybrid search quality. Use `word` tokenization (default) for body text, `lowercase` for names with hyphens or apostrophes, `field` tokenization for exact-match enums like entity types, and `trigram` for fuzzy matching. BM25 parameters (`b=0.75`, `k1=1.2`) are configured at the collection level via `inverted_index_config`. Property-level boosting in BM25 queries (e.g., `entity_names^3`) lets you weight entity name matches higher than body text matches.

**Multi-tenancy** makes sense only if serving multiple books—each book becomes a tenant sharing the same schema but with isolated data shards. Tenants support hot/warm/cold states (`ACTIVE`/`INACTIVE`/`OFFLOADED`) for managing inactive books. For chapter-level isolation within a single book, use filtered queries on `chapter_number` instead. Note that cross-references in multi-tenant collections can only target objects within the same tenant or in non-multi-tenant collections.

---

## Phase 2: GraphRAG schemas bridge vectors and knowledge graphs

Graph-augmented RAG adds entity nodes, typed relationship edges, community detection, and temporal reasoning on top of the vector store layer. Microsoft's GraphRAG, LlamaIndex's Property Graph Index, and Neo4j's GraphRAG package have converged on a remarkably consistent data model.

**Microsoft GraphRAG produces seven output artifacts**: documents, text units (chunks), entities, relationships, covariates (claims), communities, and community reports. The entity schema includes `title`, `type`, `description` (LLM-summarized from all source chunks), `text_unit_ids` (provenance links), `frequency` (mention count), and `degree` (graph connectedness). Relationships carry `source`, `target`, `type`, `description`, `weight` (LLM-derived strength), and `combined_degree`. Communities—detected via the **Hierarchical Leiden Algorithm**—contain `entity_ids`, `relationship_ids`, a `level` in the hierarchy, and LLM-generated `summary` and `full_report` fields. Three artifact types get embedded for vector search: entity descriptions, text unit text, and community report summaries.

The `text_unit_ids` array is the critical bridge between vector and graph stores. Every entity and relationship traces back to specific chunks, enabling both provenance tracking and co-occurrence analysis. Two entities co-occur when they share text_unit_ids—in Neo4j, this is modeled as `(Entity)-[:APPEARS_IN]->(TextUnit)` with co-occurrence queryable via bidirectional traversal.

**Entity resolution** should combine three strategies: name-based matching (Microsoft GraphRAG's default—entities with identical normalized names auto-merge), embedding similarity with edit distance (LlamaIndex's approach using cosine similarity plus Levenshtein distance), and alias-based matching using an `aliases` array. For biography data, context is critical for disambiguation—dates, roles, and locations help distinguish entities like two different "John" characters. The Neo4j GraphRAG package includes dedicated `EntityResolver` components that merge similar entities post-extraction.

### Schema-guided extraction dramatically improves graph quality

Both LlamaIndex's `SchemaLLMPathExtractor` and Neo4j's `SchemaBuilder` use predefined entity types, relationship types, and valid patterns to constrain LLM extraction. For a biography, define **6–8 entity types** (`PERSON`, `ORGANIZATION`, `LOCATION`, `EVENT`, `CONCEPT`, `WORK`, `ERA`) and a **validation schema** mapping which relationship types are valid between which entity types. LlamaIndex recommends `strict=False` initially to see what the LLM discovers, then tightening constraints iteratively.

A practical relationship type taxonomy for biography data spans six categories. Interpersonal relationships include `MARRIED_TO`, `PARENT_OF`, `MENTORED_BY`, `RIVAL_OF`. Organizational relationships include `MEMBER_OF`, `LEADER_OF`, `FOUNDED`, `EMPLOYED_BY`. Temporal/sequential types include `PRECEDED_BY`, `FOLLOWED_BY`, `DURING`, `CONCURRENT_WITH`. Causal types include `CAUSED`, `LED_TO`, `INFLUENCED`, `MOTIVATED_BY`. Thematic types include `SYMBOLIZES`, `EXEMPLIFIES`, `CONTRASTS_WITH`. Spatial types include `LOCATED_IN`, `BORN_IN`, `TRAVELED_TO`. Start with **15–20 relationship types** and expand as extraction reveals patterns.

### Temporal reasoning needs bi-temporal modeling and precision tracking

Temporal schema design for biography data requires three innovations beyond simple date fields. First, **temporal bounds on relationships**, not just events—a `SERVED_AS_PRESIDENT` edge needs `valid_from` and `valid_to` fields. The Graphiti/Zep framework implements a bi-temporal model where timeline T represents chronological ordering and timeline T' represents ingestion/transaction time, with old facts invalidated rather than deleted.

Second, **temporal precision tracking** is essential because biography sources vary wildly in specificity. A `date_precision` field with values like `exact`, `day`, `month`, `year`, `decade`, `approximate`, or `relative` captures whether "spring of 1923" is known to the month or just the season. Uncertainty gets its own fields: `date_earliest`, `date_latest`, and `confidence`.

Third, the TG-RAG approach (2025) models a **hierarchical time graph** (Decade→Year→Month→Day) with multi-granularity temporal summaries attached to each level. This supports both fine-grained local queries ("What happened on April 14, 1865?") and trend-level global queries ("How did the subject's career evolve in the 1860s?"). Events link to their position in this hierarchy, enabling efficient temporal range queries.

---

## JSON Schema annotations are extraction instructions, not documentation

The single highest-impact schema design decision is how you write `description` fields. Research from the PARSE paper (2025) found that **entity description enhancement accounted for 34% of all schema improvements** that boosted extraction quality, while structural reorganization (primarily flattening over-nested schemas) accounted for **55%**.

Descriptions should be instructional, not merely descriptive. Instead of `"description": "The name"`, write `"description": "The full name of the person as mentioned in the text. Use the most complete form (e.g., 'Abraham Lincoln' not 'Lincoln'). If only a partial name appears, include what is available."` Include examples that calibrate format expectations, constraints and edge cases, and negative instructions ("Do NOT use generic labels like 'related_to'"). Class-level docstrings serve as system-level extraction instructions—both Instructor and LlamaIndex pass these directly to the LLM.

**Schema structure affects extraction quality profoundly.** The DeepJSONEval benchmark (2025) shows LLMs exhibit significant performance gaps on deeply nested JSON. Keep nesting to **1–2 levels maximum**. The recommended pattern: extract entities, events, and relationships nested within chunk context (giving the LLM contextual grounding), then post-process into flat graph-ready structures using `entity_id` as the bridge. Use `Optional` fields liberally—let the model return `null` rather than forcing hallucination. Include a `reasoning` field before extraction fields to enable chain-of-thought, which OpenAI's structured outputs documentation specifically recommends.

For complex biography extraction, a **two-step approach** addresses the finding from Tam et al. (2024) that constrained JSON decoding degrades reasoning performance by 10–15%. Step one: free-form analysis without JSON constraints. Step two: structured formatting into the target schema. Use Pydantic as the single source of truth—define schemas once, generate JSON Schema automatically, and let docstrings and `Field(description=...)` flow through to the LLM.

---

## Provenance, versioning, and overlap form the operational backbone

Every extracted object—chunk, entity, relationship—needs provenance metadata tracking the full extraction lineage: `extraction_model` and version, `extraction_date`, `pipeline_version`, `schema_version`, and `confidence_score`. Store confidence at the field level where possible (entity extraction confidence vs. event extraction confidence vs. temporal normalization confidence). Neo4j's advanced RAG guide recommends down-weighting or ignoring low-confidence metadata at query time.

**Schema versioning** should follow semantic versioning: MAJOR for breaking changes (removed fields, type changes requiring reprocessing), MINOR for backward-compatible additions (new optional fields with defaults), PATCH for description-only changes. Store `schema_version` on every extracted object in both vector store and knowledge graph. Maintain a migration registry mapping version transitions to required actions. The atomic update pattern—generating new vectors with a `staging` flag while keeping old vectors active, then swapping atomically once validated—prevents retrieval degradation during re-indexing.

Embedding metadata must include `embedding_model`, `embedding_dimension`, `embedding_date`, and critically, `text_embedded`—the exact text string that was embedded. This field is essential for debugging retrieval quality and re-embedding when upgrading models. The cardinal rule: **never mix embedding models between indexing and querying**. The `embedding_model` field tells you which chunks need re-embedding after model upgrades.

For chunk overlap, assign each overlap region to one "owning" chunk (typically the earlier one) and track `overlap_tokens_prev`, `overlap_tokens_next`, and `shared_text_hash`. Entities extracted from overlap regions should carry `is_overlap_region=True` and `primary_chunk_id` to prevent double-counting in the knowledge graph. At retrieval time, FAISS requires application-level deduplication (it has no built-in support); Weaviate's `autocut` feature can help by trimming results at relevance score gaps.

---

## Conclusion

The schema designs that perform best in 2025 RAG pipelines share three characteristics that earlier approaches missed. First, they treat the schema as a **dual-format specification**—simultaneously defining vector store documents and graph nodes/edges through shared identifiers (`entity_id`, `text_unit_ids`) that bridge both storage paradigms. Second, they invest heavily in **extraction-time guidance** through JSON Schema descriptions that function as LLM instructions, with constrained vocabularies via enums and moderate nesting depths that respect LLM cognitive limits. Third, they embed **temporal and provenance metadata from ingestion onward**, recognizing that questions about "when" and "how reliably do we know this" are as common as questions about "what."

For the biography use case specifically, the most impactful additions beyond standard chunking schemas are: named vectors for content/summary/entity-context retrieval, hierarchical chunk relationships enabling auto-merging, a focused relationship taxonomy of 15–20 types with temporal bounds, community detection for global thematic queries, and a bi-temporal model that captures both narrative chronology and extraction lineage. Start with the vector-ready chunk schema and entity annotations for Phase 1, then layer on graph edges, community detection, and temporal hierarchy for Phase 2—the `entity_id` and `text_unit_ids` fields you define in Phase 1 become the exact bridge points Phase 2 needs.