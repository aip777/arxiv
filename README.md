# arXiv Papers API

Ingests arXiv papers into SQLite and serves two endpoints:

- `GET /api/stats/` – aggregated data for charts
- `POST /api/ask/` – answers questions about the papers using RAG

## Setup

```bash
cp .env.example .env        # set OPENAI_API_KEY
docker compose up -d --build
docker compose exec api python manage.py ingest_arxiv
```

The API runs on http://localhost:8000 (Swagger docs at `/api/docs/`).

Without Docker, from `backend/`: `pip install -r requirements-dev.txt`, then `python manage.py migrate`, `python manage.py ingest_arxiv` and `python manage.py runserver`.

## Environment variables

Only `OPENAI_API_KEY` is required. The rest are listed with defaults in `.env.example`, for example:

| Variable | Default |
| --- | --- |
| `ARXIV_CATEGORIES` | `cs.AI,cs.LG,cs.CL` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` |
| `LLM_MODEL` | `gpt-4.1-mini` |
| `RAG_MAX_DISTANCE` | `0.65` |

## Ingestion

```bash
python manage.py ingest_arxiv                  # fetch 1,000 papers and embed them
python manage.py ingest_arxiv --incremental    # only new or changed papers
python manage.py reset_dataset --yes           # delete everything
```

Requests are paged and sent at most once every 3 seconds. Re-running is safe: papers are upserted by arXiv id and only changed papers are re-embedded.

## API

### GET /api/stats/

Optional params: `top_n`, `interval` (`day`, `week`, `month`, `year`), `date_from`, `date_to`.

```bash
curl "http://localhost:8000/api/stats/?top_n=2"
```

```json
{
  "summary": {"total_papers": 589, "total_authors": 2837, "total_categories": 83},
  "top_categories": [{"category": "cs.LG", "paper_count": 311}, {"category": "cs.AI", "paper_count": 295}],
  "papers_over_time": {"periods": ["2026-09"], "series": [{"category": "cs.LG", "counts": [311]}]},
  "top_authors": [{"author": "Bo Wang", "paper_count": 4}],
  "authors_per_paper": {"average": 5.1, "median": 4.0}
}
```

(shortened)

### POST /api/ask/

```bash
curl -X POST http://localhost:8000/api/ask/ -H "Content-Type: application/json" \
  -d '{"question": "How do recent papers reduce hallucinations in LLMs?"}'
```

```json
{
  "answer": "... RelCheck corrects relational hallucinations in multimodal LLMs [2609.27890] ...",
  "sources": [{"arxiv_id": "2609.27890", "title": "RelCheck: Dual-Evidence Spatial Grounding for VLM Hallucination Correction", "url": "http://arxiv.org/abs/2609.27890v1", "similarity": 0.5775}]
}
```

If no paper is relevant, it says so instead of guessing: `{"answer": "I couldn't find any papers in the dataset that are relevant to this question, ...", "sources": []}`


