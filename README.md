# arXiv Papers API

This project pulls papers from the arXiv API, stores them in a database, and exposes two endpoints:

- `GET /api/stats/` returns aggregated numbers you can plug into charts.
- `POST /api/ask/` answers questions about the papers using RAG (retrieval + an LLM) and tells you which papers the answer came from.

It's built with Django, Django REST Framework, SQLite and the OpenAI API.

## Getting started

You need Docker and an OpenAI API key.

```bash
cp .env.example .env
# open .env and set OPENAI_API_KEY

docker compose up -d --build
```

That's it. The database is created and migrated when the container starts, and the API runs on http://localhost:8000.

The database starts empty, so load some papers:

```bash
docker compose exec api python manage.py ingest_arxiv
```

This fetches the 1,000 most recently updated papers from cs.AI, cs.LG and cs.CL and creates their embeddings. It takes a minute or two.

Useful URLs:

- http://localhost:8000/api/docs/ for Swagger docs
- http://localhost:8000/admin/ for browsing the data (create a user with `docker compose exec api python manage.py createsuperuser`)
- http://localhost:8000/api/health/ for the health check

## Environment variables

Everything is listed in `.env.example`. Only `OPENAI_API_KEY` is required. The rest have defaults.

| Variable | Default | What it does |
| --- | --- | --- |
| `OPENAI_API_KEY` | | Used for embeddings and answers |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible endpoint |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `LLM_MODEL` | `gpt-4.1-mini` | Model that writes the answers |
| `RAG_TOP_K` | `5` | How many papers are retrieved per question |
| `RAG_MAX_DISTANCE` | `0.65` | Papers further than this from the question are ignored |
| `ARXIV_CATEGORIES` | `cs.AI,cs.LG,cs.CL` | Categories to ingest |
| `ARXIV_REQUEST_DELAY` | `3` | Seconds between arXiv requests |
| `ARXIV_PAGE_SIZE` | `100` | Papers per arXiv request |
| `SQLITE_PATH` | `backend/data/arxiv.sqlite3` | Database file (Docker stores it in a volume) |
| `DJANGO_SECRET_KEY` | dev key | Change this outside local use |
| `DJANGO_DEBUG` | `false` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Allowed hosts |
| `API_PORT` | `8000` | Port the API is published on |
| `THROTTLE_ANON` | `300/minute` | Rate limit for every other endpoint |
| `THROTTLE_ASK` | `20/minute` | Rate limit for `/ask` |
| `LOG_LEVEL` | `INFO` | Log level for the app's own loggers |

## Loading and managing data

Run these with `docker compose exec api python manage.py <command>`.

```bash
ingest_arxiv                                   # fetch 1,000 papers and embed them
ingest_arxiv --categories cs.CL --max-results 2000
ingest_arxiv --incremental                     # only pick up new or changed papers
ingest_arxiv --skip-embeddings                 # store papers now, embed later
build_index                                    # embed anything that is missing or out of date
reset_dataset --yes                            # delete all papers, authors, categories and embeddings
```

A few things worth knowing about ingestion:

- It pages through arXiv with `start` and `max_results` and waits 3 seconds between requests, as arXiv asks. If arXiv returns an error or rate-limits the request, it retries with a growing delay.
- Running it again is safe. Papers are matched by arXiv id, so nothing gets duplicated. If a run crashes halfway, the papers saved so far stay, and the next run carries on.
- Papers are sorted by last update, so re-running picks up new papers and new versions of existing ones. When a paper's title or abstract changes, only that paper gets re-embedded.
- Broken entries in the feed are logged and skipped instead of stopping the run.
- Every run is recorded in the admin under "Scheduled task logs" with how many papers were created, updated, or unchanged.

## API

### GET /api/stats/

Returns chart-ready aggregations computed in the database:

- total papers, authors and categories
- top categories by paper count
- paper count per category over time
- top authors by paper count
- authors per paper (average, median, min, max and a distribution)

Optional query params: `top_n` (1-50, default 10), `interval` (`day`, `week`, `month` or `year`, default `month`), `date_from` and `date_to` (`YYYY-MM-DD`).

```bash
curl "http://localhost:8000/api/stats/?top_n=5&interval=month"
```

Response (shortened):

```json
{
  "filters": {"top_n": 5, "interval": "month", "date_from": null, "date_to": null},
  "summary": {
    "total_papers": 589,
    "total_authors": 2837,
    "total_categories": 83,
    "first_published": "2026-09-24",
    "last_published": "2026-09-24"
  },
  "top_categories": [
    {"category": "cs.LG", "paper_count": 311},
    {"category": "cs.AI", "paper_count": 295},
    {"category": "cs.CL", "paper_count": 165}
  ],
  "papers_over_time": {
    "interval": "month",
    "periods": ["2026-09"],
    "total": [589],
    "series": [
      {"category": "cs.LG", "counts": [311]},
      {"category": "cs.AI", "counts": [295]}
    ]
  },
  "top_authors": [
    {"author": "Bo Wang", "paper_count": 4},
    {"author": "Chao Ning", "paper_count": 4}
  ],
  "authors_per_paper": {
    "average": 5.1,
    "median": 4.0,
    "min": 1,
    "max": 75,
    "distribution": [
      {"authors": "1", "paper_count": 64},
      {"authors": "2", "paper_count": 88},
      {"authors": "10+", "paper_count": 54}
    ]
  }
}
```

In `papers_over_time`, each `counts` list lines up with `periods`, so you can pass them straight to a chart library. A paper listed in several categories is counted in each one.

### POST /api/ask/

Send a question and get an answer based only on the stored abstracts. `top_k` is optional (1-20).

```bash
curl -X POST http://localhost:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What methods are proposed to reduce hallucinations in large language models?"}'
```

Response (shortened):

```json
{
  "answer": "Several methods are proposed: ... RelCheck corrects relational hallucinations in multimodal LLMs using scene-graph and spatial evidence [2609.27890] ...",
  "sources": [
    {
      "arxiv_id": "2609.27890",
      "title": "RelCheck: Dual-Evidence Spatial Grounding for VLM Hallucination Correction",
      "authors": ["Siddhi Patil", "Navrati Saxena", "William B. Andreopoulos"],
      "primary_category": "cs.CV",
      "published": "2026-09-24",
      "url": "http://arxiv.org/abs/2609.27890v1",
      "similarity": 0.5775
    }
  ]
}
```

`sources` only lists papers the answer actually cites.

If the question has nothing to do with the papers, the API says so and skips the LLM:

```json
{"answer": "I couldn't find any papers in the dataset that are relevant to this question, so I can't answer it from the available data.", "sources": []}
```

If the papers are on topic but don't contain the answer, the model says that too:

```json
{"answer": "The provided papers do not mention the exact training cost in dollars of GPT-4.", "sources": []}
```

Errors:

- `400` for an invalid request, e.g. a missing or too short question
- `429` when the rate limit is hit
- `503` when no papers have been embedded yet, or OpenAI can't be reached

## How it works

```
arXiv API -> client (paging, throttling, retries) -> parser (clean up) -> SQLite
                                                                             |
                                                        embeddings (OpenAI) --+
/api/stats/ -> SQL aggregations
/api/ask/   -> embed question -> find closest abstracts -> LLM answers from them
```

The code lives in `backend/`:

- `papers/` has the models, arXiv client, parser, ingestion and the stats endpoint.
- `rag/` has embeddings, vector search and the ask endpoint. All OpenAI calls go through `rag/services/llm.py`.
- `basebox/` holds shared pieces: error logging, the task log and the health check.
- `pconfig/` holds the Django settings.

### Database schema

- `papers_category`: arXiv category code, e.g. `cs.AI`
- `papers_author`: author name
- `papers_paper`: arXiv id, version, title, abstract, primary category, published and updated dates, DOI, journal ref, comment, links
- `papers_paper_categories`: links papers to all of their categories
- `papers_paperauthor`: links papers to authors, keeping author order
- `rag_paperembedding`: one vector per paper (title + abstract), plus which model made it and a hash of the text it was built from

Migrations are in each app's `migrations/` folder.

### A few decisions

- **SQLite for everything.** The papers and the vectors live in one file, so there's no separate database to run. Vectors are stored as bytes and searched with numpy. For a few thousand papers that's fast and exact.
- **One embedding per paper.** Abstracts are short, so I didn't split them into chunks.
- **Avoiding made-up answers.** Papers that aren't close enough to the question are dropped before the LLM sees anything. If none are left, the API answers "no relevant papers" by itself. Otherwise the LLM is told to use only the given papers, cite them, and say when it can't answer. The 0.65 cut-off comes from testing. Relevant questions scored between 0.37 and 0.54, and unrelated ones scored 0.82 or more.

## Running without Docker

```bash
cp .env.example .env            # and set OPENAI_API_KEY
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python manage.py migrate
python manage.py collectstatic --noinput   # needed for the admin when DJANGO_DEBUG=false
python manage.py ingest_arxiv
python manage.py runserver
```

The database file is created at `backend/data/arxiv.sqlite3`. If you see `no such table`, you skipped `migrate`.

## Tests

```bash
docker compose exec api pytest
# or locally, from backend/
pytest
```

There are 78 tests covering the parser, the arXiv client (paging, throttling, retries), ingestion (re-runs, updates, failures, reset), the vector search and indexing, both endpoints, and error cases. OpenAI is replaced with a fake in tests, so they run offline in a few seconds.

## Known limitations

- arXiv rate-limits hard. If you send too many requests, your IP can get blocked for a while with HTTP 406. The client retries, but a long block ends the run. Just run it again later, and it continues from where it stopped.
- Authors are matched by name, so two people with the same name count as one.
- `/ask` only knows the abstracts, not full papers. For questions like "how many papers..." use `/api/stats/`.
- `--incremental` stops at the first page with nothing new. If a previous run crashed halfway, run once without it.
- The vector search checks every paper, which is fine up to tens of thousands of papers.
- SQLite handles one writer at a time. That's fine here, but not for heavy concurrent writes.
- With SQLite there's no separate database container. The database is a file inside the API container, kept on a Docker volume.

## What I'd improve with more time

- Mix keyword search (SQLite FTS5) with vector search and add a reranker
- Let `/ask` filter by category, date or author
- Run incremental ingestion on a schedule
- Build a small set of test questions to measure and tune retrieval
- Cache the stats response and add CI for tests and lint
