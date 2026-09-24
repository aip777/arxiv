# arXiv Papers: Ingest, Store, Visualize, and Ask

A Django + SQLite service that:

1. **Ingests** papers from the live arXiv API (paginated, throttled, retry-safe, incremental).
2. **Normalizes** the Atom/XML feed into papers, authors and categories.
3. **Stores** them in a relational schema with migrations.
4. **Serves one visualization API** (`GET /api/stats/`) with chart-ready aggregates computed in the database.
5. **Answers questions** with RAG (`POST /api/ask/`): vector similarity search over abstracts plus an LLM
   that must answer only from the retrieved papers and cite them.

---

## Quick start (Docker)

```bash
cp .env.example .env          # then set OPENAI_API_KEY in .env
docker compose up -d --build  # builds and starts the API; the SQLite database is created and migrated on start
docker compose exec api python manage.py ingest_arxiv   # ~1,000 papers + embeddings, takes ~1-2 minutes
```

The API is then available at http://localhost:8000:

| URL | What |
| --- | --- |
| `GET  /api/stats/` | Aggregated statistics for charts |
| `POST /api/ask/` | RAG question answering |
| `GET  /api/health/` | Health check (used by Docker) |
| `/api/docs/` | Swagger UI (OpenAPI schema at `/api/schema/`) |
| `/admin/` | Django admin for browsing papers (`docker compose exec api python manage.py createsuperuser`) |

Run the tests inside the container:

```bash
docker compose exec api pytest
```

## Environment variables

All variables are listed in [`.env.example`](.env.example). Only `OPENAI_API_KEY` has to be filled in.

| Variable | Default | Purpose |
| --- | --- | --- |
| `SQLITE_PATH` | `backend/data/arxiv.sqlite3` | Database file. Compose puts it on the `sqlite-data` volume |
| `DJANGO_SECRET_KEY` | insecure dev key | Set a real value outside local use |
| `DJANGO_DEBUG` | `false` | Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma separated |
| `API_PORT` | `8000` | Host port for the API |
| `OPENAI_API_KEY` | – | Required for embeddings and answers |
| `OPENAI_BASE_URL` | – | Optional OpenAI-compatible endpoint |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Changing it re-embeds everything on the next sync |
| `LLM_MODEL` | `gpt-4.1-mini` | Chat model used to write answers |
| `RAG_TOP_K` | `5` | Papers retrieved per question (overridable per request, max 20) |
| `RAG_MAX_DISTANCE` | `0.65` | Cosine-distance cut-off for "relevant" |
| `ARXIV_CATEGORIES` | `cs.AI,cs.LG,cs.CL` | Default categories to ingest |
| `ARXIV_REQUEST_DELAY` | `3` | Seconds between arXiv requests (arXiv asks for ≥ 3) |
| `ARXIV_PAGE_SIZE` | `100` | Results per arXiv request |
| `THROTTLE_ANON` / `THROTTLE_ASK` | `300/minute` / `20/minute` | API rate limits (`/ask` is stricter because it calls a paid LLM) |
| `LOG_LEVEL` | `INFO` | Log level for the app loggers |

## Ingestion and data management

All commands run with `docker compose exec api python manage.py <command>` (or `python manage.py <command>` locally).

```bash
# Default run: 1,000 most recently updated papers from cs.AI, cs.LG, cs.CL, then embed them
python manage.py ingest_arxiv

# Choose categories / size
python manage.py ingest_arxiv --categories cs.CL stat.ML --max-results 2000 --page-size 200

# Refresh: pick up new and changed papers only, stop once a page has nothing new
python manage.py ingest_arxiv --incremental

# Store papers without calling the embedding API, embed later
python manage.py ingest_arxiv --skip-embeddings
python manage.py build_index

# Wipe papers, authors, categories and embeddings for a clean re-import
python manage.py reset_dataset --yes
```

How the requirements are met:

- **Pagination and throttling.** Requests go through `start`/`max_results` pages sorted by `lastUpdatedDate`
  (newest first). The client waits at least `ARXIV_REQUEST_DELAY` seconds between requests. It retries
  network errors and throttling responses (406/429/5xx) with exponential backoff, and retries the empty
  pages arXiv sometimes returns in the middle of a result set.
- **Safe re-runs.** Each paper is upserted in its own transaction on its version-less `arxiv_id`.
  Re-running never duplicates rows. A crash part-way keeps everything stored so far, and the next run
  continues. A malformed entry is logged and skipped, and one failing paper doesn't stop the batch.
- **Updates.** A stored paper is updated when any field, author order or category changed, for example
  a new version, DOI or journal reference. Each paper keeps a SHA-256 `content_hash` of title and
  abstract. Its embedding stores the hash it was built from. After ingestion, `build_index` logic
  re-embeds only papers with a missing or stale vector, or all of them if `EMBEDDING_MODEL` changed.
- **Run log.** Every run is recorded in `ScheduledTaskLog` with status and counts
  (`created / updated / unchanged / skipped / failed`), visible in the admin.

## API

### `GET /api/stats/` – visualization data

Query parameters (all optional):

| Param | Default | Notes |
| --- | --- | --- |
| `top_n` | `10` | 1–50, size of the top-N lists |
| `interval` | `month` | `day`, `week`, `month` or `year` for the time series |
| `date_from`, `date_to` | – | `YYYY-MM-DD`, filter on published date |

Returns five aggregations, all computed in the database with SQL aggregation:

- `summary`: totals and the published-date range.
- `top_categories`: papers per category, counting every category a paper is cross-listed in.
- `papers_over_time`: papers per period for the top 5 categories plus an overall `total`. Returned as
  aligned arrays that chart libraries take directly. Only periods with data are listed.
- `top_authors`: most prolific authors.
- `authors_per_paper`: average, median, min, max and a distribution (10+ bucketed).

```bash
curl 'http://localhost:8000/api/stats/?top_n=5&interval=month'
```

SAMPLE_STATS_RESPONSE

Invalid parameters return `400`:

```bash
curl 'http://localhost:8000/api/stats/?interval=decade'
# {"detail":{"interval":["\"decade\" is not a valid choice."]}}
```

### `POST /api/ask/` – RAG question answering

Body: `{"question": "...", "top_k": 5}` (`top_k` optional, 1–20). `question` is 3–1000 characters.

```bash
curl -X POST http://localhost:8000/api/ask/ \
  -H 'Content-Type: application/json' \
  -d '{"question": "How are large language model agents being evaluated?"}'
```

SAMPLE_ASK_RESPONSE

When nothing in the dataset is relevant, the API says so. It does not call the LLM in that case, and it
returns no sources:

SAMPLE_NO_MATCH_RESPONSE

| Status | When |
| --- | --- |
| `200` | Answer produced, or an honest "no relevant papers" answer |
| `400` | Invalid body (`{"detail": {"question": [...]}}`) |
| `429` | More than `THROTTLE_ASK` requests per minute from one client |
| `503` | Index is empty (run ingestion), or the LLM / embedding provider is unavailable |

## Architecture

```
               ┌──────────── manage.py ingest_arxiv ────────────┐
arXiv API ──►  │ ArxivClient ─► parser ─► ingestion (upsert) ──►│──► SQLite
 (Atom XML)    │  throttle,     clean,    per-paper tx,         │     papers / authors / categories
               │  retry         dedupe    change detection      │     paper_embedding (float32 blobs)
               └───────────────► indexing.sync_index ──► OpenAI embeddings
                                                                        ▲
GET  /api/stats/ ──► stats service (ORM aggregation) ───────────────────┤
POST /api/ask/   ──► embed question ─► numpy cosine scan ─► distance cut-off ─► LLM (JSON: answer + cited ids)
```

Code layout (`backend/`):

| Path | Responsibility |
| --- | --- |
| `pconfig/` | Settings (environment driven), URLs, DRF and logging config |
| `basebox/` | Shared pieces: timestamp base model, `ScheduledTaskLog`, `ErrorLog` + DB log handler, exception handler, health check |
| `papers/services/arxiv_client.py` | HTTP client: pagination, throttling, retries |
| `papers/services/parser.py` | Atom XML to `PaperRecord` (normalization, validation) |
| `papers/services/ingestion.py` | Idempotent upserts, run bookkeeping, dataset reset |
| `papers/services/stats.py` | Aggregations for `/api/stats/` |
| `rag/services/llm.py` | The only place that talks to OpenAI |
| `rag/services/indexing.py` | Detects stale vectors and (re-)embeds them in batches |
| `rag/services/qa.py` | Retrieval, prompt, grounding and no-match handling |

### Schema

```
category(id, code UNIQUE)
author(id, name UNIQUE)
paper(id, arxiv_id UNIQUE, version, title, abstract, primary_category_id → category,
      published, updated, doi NULL, journal_ref NULL, comment NULL, abs_url, pdf_url, content_hash)
paper_categories(paper_id → paper, category_id → category)            -- M2M, all cross-lists
paper_author(paper_id → paper, author_id → author, position)          -- ordered author list
    UNIQUE(paper_id, position), UNIQUE(paper_id, author_id)
paper_embedding(paper_id PK → paper ON DELETE CASCADE, embedding BLOB,
                model INDEXED, content_hash)             -- L2-normalised float32 vector
```

`published` and `updated` are indexed for the time-series queries. All timestamps are stored in UTC.
Migrations live in each app's `migrations/` folder. The `rag` migration also creates the `vector`
extension, so `migrate` builds the whole schema from scratch.

## Key decisions

- **Django + DRF on SQLite.** One file holds both the relational data and the vectors, so there is
  no separate database service. Wiping the dataset is one transaction. WAL mode lets the API keep
  reading while ingestion writes.
- **Vector search without an extension.** Embeddings are stored L2-normalised as float32 blobs.
  A query is an exact cosine scan in numpy, a single matrix product. At a few thousand abstracts
  that takes milliseconds and is exact rather than approximate.
- **One embedding per paper (title + abstract).** Abstracts are short, around 150–300 words, so
  chunking would add complexity without better recall.
- **Grounding.** Retrieval keeps only papers within `RAG_MAX_DISTANCE`. The prompt tells the model to
  use only the given papers, treat their text as data, cite ids, and return `answerable: false` when the
  papers don't cover the question. Only papers the model actually cited are returned as `sources`.
- **Honest no-match.** If nothing clears the distance cut-off, the API returns a fixed "couldn't find
  relevant papers" answer without calling the LLM. That makes a made-up answer impossible in that case.
- **Provider isolation.** All OpenAI calls sit in `rag/services/llm.py`. Tests replace it with a
  deterministic bag-of-words embedder, so retrieval tests run the real vector search offline.
- **Category counting.** The stats use all categories a paper is listed in, not only the primary one,
  because cross-listing is how arXiv expresses topic overlap.

## Assumptions

- "At least 1,000 papers" is met by the most recently **updated** papers across the chosen categories.
  Sorting by `lastUpdatedDate` is what makes incremental refreshes possible.
- Authors are identified by normalized name, since arXiv has no author ids. Two people with the same
  name are merged.
- The APIs are public and read-only apart from `/ask`, so there is no authentication. `/ask` is
  rate-limited instead.
- The brief asks for `docker compose up` to bring up "the database and the API". With SQLite the
  database is a file inside the API container, kept on the `sqlite-data` named volume, so compose runs a
  single service. It is still created and migrated automatically on start.

## Local development without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend      # settings read ../.env automatically; the database goes to backend/data/
python manage.py migrate
python manage.py ingest_arxiv
python manage.py runserver
pytest          # uses an in-memory SQLite database
ruff check .
```

## Testing

CHECK_TEST_COUNT tests (`pytest`) cover:

- **Parser:** whitespace cleanup, version stripping, old-style ids, missing DOI or journal ref, author
  de-duplication, primary category handling, malformed entries, API error feeds.
- **arXiv client:** pagination, the 3-second throttle, backoff on 5xx, 429 and network errors, retry
  limits, transient empty pages.
- **Ingestion:** idempotent re-runs, in-place updates, author reordering, per-record failure isolation,
  incremental stop, failed-run logging with partial progress kept, the `ingest_arxiv` and
  `reset_dataset` commands.
- **Vector search:** normalisation, cosine ordering, model filtering, dimension checks.
- **Indexing:** batch embedding, no-op when up to date, re-embedding on abstract change but not on
  metadata change, model change.
- **APIs:** every stats aggregation against a hand-counted dataset, parameter validation, `/ask` with
  grounded answers, no-match without an LLM call, "not answerable" handling, citation fallback,
  `top_k`, validation errors, empty index, provider failure, rate limiting, JSON 404 and health.

## Known limitations

- arXiv throttles aggressively. Bursts of requests can get an IP temporarily refused with HTTP 406 for
  a while. The client backs off and retries, but a long block ends the run with a clear error. Stored
  papers are kept, and re-running resumes.
- Author identity is name-based, see Assumptions.
- `/ask` retrieves from abstracts only, so it can't answer questions about full-text details. It also
  isn't meant for questions about the whole dataset, like "how many papers…"; `/api/stats/` covers those.
- The time series only lists periods that have data. It doesn't zero-fill gaps.
- Vector search is a brute-force scan. It stays fast up to tens of thousands of papers. Beyond that,
  an ANN index such as sqlite-vec or FAISS would be needed.
- SQLite allows one writer at a time. That is fine for one ingestion process and a read-heavy API, but
  it would not suit many concurrent writers.
- Ingestion runs synchronously from the CLI. There is no scheduler or API trigger.

## What I'd improve with more time

- Hybrid retrieval: combine BM25 via SQLite FTS5 with vectors, and add a reranker.
- Metadata filters on `/ask`, for example category, date range or author, applied in the SQL
  before vector ranking.
- Scheduled incremental ingestion with Celery beat or cron, plus a run-status endpoint.
- Author disambiguation, using ORCID where available or affiliation heuristics.
- An evaluation set of question/expected-paper pairs to tune `RAG_MAX_DISTANCE` and `top_k`, and to
  catch retrieval regressions.
- Response caching for `/api/stats/`, streaming answers for `/ask`, and CI running lint and tests.
