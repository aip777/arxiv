# arXiv Papers API

Pulls papers from the arXiv API, stores them in SQLite and serves two endpoints:

- `GET /api/stats/` – aggregated data for charts
- `POST /api/ask/` – answers questions about the papers with RAG and lists the papers it used

Built with Django, Django REST Framework and the OpenAI API.

## Setup

You need Docker and an OpenAI API key.

```bash
cp .env.example .env        # set OPENAI_API_KEY
docker compose up -d --build
docker compose exec api python manage.py ingest_arxiv
```

The API runs on http://localhost:8000. Migrations run when the container starts. `ingest_arxiv` loads 1,000 papers from cs.AI, cs.LG and cs.CL and embeds them.

- Swagger docs: http://localhost:8000/api/docs/
- Admin: http://localhost:8000/admin/ (`docker compose exec api python manage.py createsuperuser`)

### Without Docker

```bash
cp .env.example .env        # set OPENAI_API_KEY
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py ingest_arxiv
python manage.py runserver
```

## Environment variables

Only `OPENAI_API_KEY` is required. The full list with defaults is in `.env.example`.

| Variable | Default | |
| --- | --- | --- |
| `OPENAI_API_KEY` | | Used for embeddings and answers |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | |
| `LLM_MODEL` | `gpt-4.1-mini` | |
| `RAG_TOP_K` | `5` | Papers retrieved per question |
| `RAG_MAX_DISTANCE` | `0.65` | Papers further than this from the question are ignored |
| `ARXIV_CATEGORIES` | `cs.AI,cs.LG,cs.CL` | Categories to ingest |
| `SQLITE_PATH` | `backend/data/arxiv.sqlite3` | Docker keeps it on a volume |

## Managing data

Run with `docker compose exec api python manage.py <command>` (or `python manage.py` locally).

```bash
ingest_arxiv                          # fetch 1,000 papers and embed them
ingest_arxiv --max-results 2000 --categories cs.CL
ingest_arxiv --incremental            # only new or changed papers
build_index                           # embed papers that are missing or out of date
reset_dataset --yes                   # delete papers, authors, categories and embeddings
```

- Requests are paged with `start`/`max_results`, sent at most once every 3 seconds, and retried with backoff when arXiv throttles.
- Re-running is safe: papers are upserted by arXiv id, and only papers whose title or abstract changed are re-embedded.
- Malformed entries are skipped and logged. Each run is recorded in the admin under "Scheduled task logs".

## API

### GET /api/stats/

Query params (all optional): `top_n` (default 10), `interval` (`day`, `week`, `month`, `year`), `date_from`, `date_to`.

```bash
curl "http://localhost:8000/api/stats/?top_n=3"
```

```json
{
  "filters": {"top_n": 3, "interval": "month", "date_from": null, "date_to": null},
  "summary": {"total_papers": 589, "total_authors": 2837, "total_categories": 83,
              "first_published": "2026-09-24", "last_published": "2026-09-24"},
  "top_categories": [
    {"category": "cs.LG", "paper_count": 311},
    {"category": "cs.AI", "paper_count": 295},
    {"category": "cs.CL", "paper_count": 165}
  ],
  "papers_over_time": {
    "interval": "month",
    "periods": ["2026-09"],
    "total": [589],
    "series": [{"category": "cs.LG", "counts": [311]}, {"category": "cs.AI", "counts": [295]}]
  },
  "top_authors": [{"author": "Bo Wang", "paper_count": 4}],
  "authors_per_paper": {"average": 5.1, "median": 4.0, "min": 1, "max": 75,
                        "distribution": [{"authors": "1", "paper_count": 64}, {"authors": "10+", "paper_count": 54}]}
}
```

Each `counts` list lines up with `periods`. A paper in several categories counts once in each.

### POST /api/ask/

```bash
curl -X POST http://localhost:8000/api/ask/ -H "Content-Type: application/json" \
  -d '{"question": "How do recent papers reduce hallucinations in LLMs?"}'
```

```json
{
  "answer": "... RelCheck corrects relational hallucinations in multimodal LLMs using scene-graph and spatial evidence [2609.27890] ...",
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

If no paper is close enough to the question, the LLM isn't called:

```json
{"answer": "I couldn't find any papers in the dataset that are relevant to this question, so I can't answer it from the available data.", "sources": []}
```

Optional `top_k` (1-20). Errors: `400` invalid input, `429` rate limit, `503` no embeddings yet or OpenAI unavailable.

## How it works

```
ingest_arxiv:  arXiv API -> parser -> SQLite (papers, authors, categories) -> OpenAI embeddings
/api/stats/:   SQL aggregations
/api/ask/:     embed question -> nearest abstracts -> LLM answers from them only
```

- `papers/` – models, arXiv client, parser, ingestion, stats endpoint
- `rag/` – embeddings, vector search, ask endpoint
- `basebox/` – error logging, run history, health check
- `pconfig/` – settings

**Schema:** `paper`, `author` and `category` tables, a `paper_categories` join table, `paperauthor` (keeps author order) and `paperembedding` (one vector per paper, with the model and a hash of the text it came from).

**Decisions:**
- Vectors are stored in SQLite and searched with numpy. For a few thousand abstracts that is fast and needs no extra service.
- One embedding per paper (title + abstract); abstracts are short enough not to chunk.
- To avoid made-up answers, papers beyond the distance cut-off never reach the LLM, and the prompt tells it to answer only from the given papers and cite them. In testing, relevant questions were at distance 0.37-0.54 and unrelated ones above 0.82.

## Tests

```bash
cd backend && pytest        # or: docker compose exec api pytest
```

OpenAI is faked in tests, so they run offline.

## Known limitations

- arXiv blocks IPs that send too many requests (HTTP 406). The run stops, and re-running later continues where it left off.
- Authors are matched by name, so two people with the same name are one author.
- `/ask` only sees abstracts. Counting questions belong to `/api/stats/`.
- Vector search scans every paper and SQLite allows one writer at a time. Fine at this size, not for large datasets.

## With more time

- Hybrid keyword + vector search with a reranker
- Filters on `/ask` (category, date, author)
- Scheduled incremental ingestion
- A small question set to measure retrieval quality, and CI
