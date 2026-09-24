from datetime import UTC, datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from papers.services.ingestion import IngestionStats, ingest_records

pytestmark = pytest.mark.django_db


def at(year, month, day):
    return datetime(year, month, day, tzinfo=UTC)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def dataset(make_record):
    """Four papers across two months with a known author/category spread."""
    records = [
        make_record("2401.00001", published=at(2024, 1, 5), authors=["Alice", "Bob"],
                    primary_category="cs.LG", categories=["cs.LG", "cs.AI"]),
        make_record("2401.00002", published=at(2024, 1, 20), authors=["Alice"],
                    primary_category="cs.LG", categories=["cs.LG"]),
        make_record("2402.00001", published=at(2024, 2, 3), authors=["Alice", "Carol", "Dan"],
                    primary_category="cs.CL", categories=["cs.CL", "cs.LG"]),
        make_record("2402.00002", published=at(2024, 2, 14), authors=["Bob", "Carol", "Dan", "Eve"],
                    primary_category="cs.AI", categories=["cs.AI"]),
    ]
    ingest_records(records, IngestionStats())


def get_stats(client, **params):
    response = client.get(reverse("stats"), params)
    assert response.status_code == 200, response.content
    return response.json()


def test_stats_on_empty_database(client):
    data = get_stats(client)
    assert data["summary"]["total_papers"] == 0
    assert data["top_categories"] == []
    assert data["papers_over_time"]["periods"] == []
    assert data["top_authors"] == []
    assert data["authors_per_paper"]["average"] is None


def test_summary_and_top_categories(client, dataset):
    data = get_stats(client)

    assert data["summary"] == {
        "total_papers": 4,
        "total_authors": 5,
        "total_categories": 3,
        "first_published": "2024-01-05",
        "last_published": "2024-02-14",
    }
    assert data["top_categories"] == [
        {"category": "cs.LG", "paper_count": 3},
        {"category": "cs.AI", "paper_count": 2},
        {"category": "cs.CL", "paper_count": 1},
    ]


def test_papers_over_time_by_month(client, dataset):
    series = get_stats(client, interval="month")["papers_over_time"]

    assert series["interval"] == "month"
    assert series["periods"] == ["2024-01", "2024-02"]
    assert series["total"] == [2, 2]
    by_category = {s["category"]: s["counts"] for s in series["series"]}
    assert by_category == {"cs.LG": [2, 1], "cs.AI": [1, 1], "cs.CL": [0, 1]}


def test_papers_over_time_by_year(client, dataset):
    series = get_stats(client, interval="year")["papers_over_time"]
    assert series["periods"] == ["2024"]
    assert series["total"] == [4]


def test_top_authors_respects_top_n(client, dataset):
    data = get_stats(client, top_n=2)
    assert data["top_authors"] == [
        {"author": "Alice", "paper_count": 3},
        {"author": "Bob", "paper_count": 2},
    ]
    assert len(data["top_categories"]) == 2


def test_authors_per_paper(client, dataset):
    stats = get_stats(client)["authors_per_paper"]
    assert stats["average"] == 2.5
    assert stats["median"] == 2.5
    assert stats["min"] == 1
    assert stats["max"] == 4
    assert stats["distribution"] == [
        {"authors": "1", "paper_count": 1},
        {"authors": "2", "paper_count": 1},
        {"authors": "3", "paper_count": 1},
        {"authors": "4", "paper_count": 1},
    ]


def test_date_filters(client, dataset):
    data = get_stats(client, date_from="2024-02-01", date_to="2024-02-28")
    assert data["summary"]["total_papers"] == 2
    assert data["filters"]["date_from"] == "2024-02-01"
    assert data["papers_over_time"]["periods"] == ["2024-02"]


@pytest.mark.parametrize("params", [
    {"top_n": 0},
    {"top_n": 500},
    {"interval": "decade"},
    {"date_from": "not-a-date"},
    {"date_from": "2024-03-01", "date_to": "2024-01-01"},
])
def test_invalid_parameters_return_400(client, params):
    response = client.get(reverse("stats"), params)
    assert response.status_code == 400
    assert "detail" in response.json()
