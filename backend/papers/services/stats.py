"""
Aggregations for the charting API. All counting happens in the database.

Category counts use every category a paper is listed under (not only its
primary one), since cross-listing is how arXiv expresses topic overlap.
"""

from datetime import date

from django.db.models import Count, IntegerField, Max, Min, OuterRef, Subquery
from django.db.models.functions import Trunc

from papers.models import Paper, PaperAuthor

INTERVALS = ("day", "week", "month", "year")
PERIOD_FORMATS = {"day": "%Y-%m-%d", "week": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}
# Keep the time series readable: one line per top category, capped at this many.
MAX_SERIES = 5
# Author counts above this are grouped into one "N+" bucket in the distribution.
MAX_AUTHOR_BUCKET = 10

PaperCategory = Paper.categories.through


def filtered_papers(date_from: date | None = None, date_to: date | None = None):
    papers = Paper.objects.all()
    if date_from:
        papers = papers.filter(published__date__gte=date_from)
    if date_to:
        papers = papers.filter(published__date__lte=date_to)
    return papers


def summary(papers) -> dict:
    bounds = papers.aggregate(first=Min("published"), last=Max("published"))
    return {
        "total_papers": papers.count(),
        "total_authors": PaperAuthor.objects.filter(paper__in=papers).values("author").distinct().count(),
        "total_categories": PaperCategory.objects.filter(paper__in=papers).values("category").distinct().count(),
        "first_published": bounds["first"].date().isoformat() if bounds["first"] else None,
        "last_published": bounds["last"].date().isoformat() if bounds["last"] else None,
    }


def top_categories(papers, top_n: int) -> list[dict]:
    rows = (
        PaperCategory.objects.filter(paper__in=papers)
        .values("category__code")
        .annotate(paper_count=Count("paper_id"))
        .order_by("-paper_count", "category__code")[:top_n]
    )
    return [{"category": row["category__code"], "paper_count": row["paper_count"]} for row in rows]


def papers_over_time(papers, interval: str, categories: list[str]) -> dict:
    """
    Paper counts per period for the given categories, plus the overall total.

    Returned as aligned arrays (one value per entry in `periods`), which is the
    shape most chart libraries take directly. Only periods with data appear.
    """
    period = Trunc("paper__published", interval)
    rows = (
        PaperCategory.objects.filter(paper__in=papers, category__code__in=categories)
        .annotate(period=period)
        .values("period", "category__code")
        .annotate(paper_count=Count("paper_id"))
    )
    totals = (
        papers.annotate(period=Trunc("published", interval))
        .values("period")
        .annotate(paper_count=Count("id"))
        .order_by("period")
    )

    fmt = PERIOD_FORMATS[interval]
    periods = [row["period"].strftime(fmt) for row in totals]
    index = {label: i for i, label in enumerate(periods)}

    counts = {code: [0] * len(periods) for code in categories}
    for row in rows:
        counts[row["category__code"]][index[row["period"].strftime(fmt)]] = row["paper_count"]

    return {
        "interval": interval,
        "periods": periods,
        "total": [row["paper_count"] for row in totals],
        "series": [{"category": code, "counts": counts[code]} for code in categories],
    }


def top_authors(papers, top_n: int) -> list[dict]:
    rows = (
        PaperAuthor.objects.filter(paper__in=papers)
        .values("author__name")
        .annotate(paper_count=Count("paper_id"))
        .order_by("-paper_count", "author__name")[:top_n]
    )
    return [{"author": row["author__name"], "paper_count": row["paper_count"]} for row in rows]


def _value_at(rows: list[dict], position: int) -> int:
    """Author count of the paper at `position` when papers are sorted by author count."""
    seen = 0
    for row in rows:
        seen += row["paper_count"]
        if position < seen:
            return row["author_count"]
    return rows[-1]["author_count"]


def authors_per_paper(papers) -> dict:
    author_count = Subquery(
        PaperAuthor.objects.filter(paper=OuterRef("pk")).values("paper").annotate(n=Count("id")).values("n"),
        output_field=IntegerField(),
    )
    rows = list(
        papers.annotate(author_count=author_count)
        .values("author_count")
        .annotate(paper_count=Count("id"))
        .order_by("author_count")
    )
    rows = [row for row in rows if row["author_count"]]
    total_papers = sum(row["paper_count"] for row in rows)
    if not total_papers:
        return {"average": None, "median": None, "min": None, "max": None, "distribution": []}

    total_authorships = sum(row["author_count"] * row["paper_count"] for row in rows)
    median = (_value_at(rows, (total_papers - 1) // 2) + _value_at(rows, total_papers // 2)) / 2

    buckets: dict[str, int] = {}
    for row in rows:
        n = row["author_count"]
        label = str(n) if n < MAX_AUTHOR_BUCKET else f"{MAX_AUTHOR_BUCKET}+"
        buckets[label] = buckets.get(label, 0) + row["paper_count"]

    return {
        "average": round(total_authorships / total_papers, 2),
        "median": median,
        "min": rows[0]["author_count"],
        "max": rows[-1]["author_count"],
        "distribution": [{"authors": label, "paper_count": count} for label, count in buckets.items()],
    }


def build_stats(
    top_n: int = 10, interval: str = "month", date_from: date | None = None, date_to: date | None = None
) -> dict:
    papers = filtered_papers(date_from, date_to)
    categories = top_categories(papers, top_n)
    series_categories = [row["category"] for row in categories[:MAX_SERIES]]
    return {
        "filters": {
            "top_n": top_n,
            "interval": interval,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
        "summary": summary(papers),
        "top_categories": categories,
        "papers_over_time": papers_over_time(papers, interval, series_categories),
        "top_authors": top_authors(papers, top_n),
        "authors_per_paper": authors_per_paper(papers),
    }
