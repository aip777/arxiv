import pytest
import requests

from papers.services import arxiv_client
from papers.services.arxiv_client import ArxivClient, ArxivClientError, build_category_query

EMPTY_FEED = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
  <opensearch:totalResults>{total}</opensearch:totalResults>
</feed>"""


class FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class FakeSession:
    """Returns queued responses (or raises queued exceptions) and records request params."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append(dict(params))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def time(self):
        return self.now


def make_client(responses, **kwargs):
    clock = FakeClock()
    session = FakeSession(responses)
    client = ArxivClient(
        base_url="http://arxiv.test/api/query",
        delay=3,
        max_retries=2,
        timeout=5,
        session=session,
        sleep=clock.sleep,
        clock=clock.time,
        **kwargs,
    )
    return client, session, clock


def test_build_category_query():
    assert build_category_query(["cs.AI", " cs.LG "]) == "cat:cs.AI OR cat:cs.LG"
    assert build_category_query(["hep-th", "astro-ph.CO"]) == "cat:hep-th OR cat:astro-ph.CO"
    with pytest.raises(ValueError):
        build_category_query([])


@pytest.mark.parametrize("category", ["cs.AI OR all:x", "cs.AI)", "cat:cs.AI", "CS AI"])
def test_build_category_query_rejects_injection(category):
    with pytest.raises(ValueError, match="Invalid arXiv category"):
        build_category_query([category])


def test_paginates_until_max_results_and_throttles(atom_feed):
    # Each fixture page has 3 entries and claims 3 total; bump total so paging continues.
    feed = atom_feed.replace("<opensearch:totalResults>3", "<opensearch:totalResults>100")
    client, session, clock = make_client([FakeResponse(text=feed), FakeResponse(text=feed)])

    pages = list(client.iter_pages(["cs.AI", "cs.LG"], max_results=5, page_size=3))

    assert len(pages) == 2
    assert [call["start"] for call in session.calls] == [0, 3]
    assert [call["max_results"] for call in session.calls] == [3, 2]
    assert session.calls[0]["search_query"] == "cat:cs.AI OR cat:cs.LG"
    assert session.calls[0]["sortBy"] == "lastUpdatedDate"
    # The second request waited out the 3 second politeness delay.
    assert clock.sleeps == [3]


def test_stops_when_total_results_reached(atom_feed):
    client, session, _ = make_client([FakeResponse(text=atom_feed)])
    pages = list(client.iter_pages(["cs.AI"], max_results=1000, page_size=100))
    assert len(pages) == 1
    assert len(session.calls) == 1


def test_retries_throttled_and_failed_requests(atom_feed):
    client, session, clock = make_client(
        [
            FakeResponse(status_code=503),
            requests.ConnectionError("boom"),
            FakeResponse(text=atom_feed),
        ]
    )
    page = client.fetch_page("cat:cs.AI", start=0, max_results=3)
    assert len(page.records) == 2
    assert len(session.calls) == 3
    # Exponential backoff: 3s then 6s.
    assert clock.sleeps == [3, 6]


def test_gives_up_after_max_retries():
    client, _, _ = make_client([FakeResponse(status_code=429)] * 3)
    with pytest.raises(ArxivClientError, match="after 3 attempts"):
        client.fetch_page("cat:cs.AI", start=0, max_results=3)


def test_non_retryable_status_fails_immediately():
    client, session, _ = make_client([FakeResponse(status_code=400, text="bad query")])
    with pytest.raises(ArxivClientError, match="HTTP 400"):
        client.fetch_page("cat:cs.AI", start=0, max_results=3)
    assert len(session.calls) == 1


def test_retries_transient_empty_page_then_continues(atom_feed):
    client, session, _ = make_client(
        [
            FakeResponse(text=EMPTY_FEED.format(total=3)),
            FakeResponse(text=atom_feed),
        ]
    )
    pages = list(client.iter_pages(["cs.AI"], max_results=3, page_size=3))
    assert len(pages) == 1
    assert len(session.calls) == 2


def test_empty_result_set_yields_nothing():
    client, _, _ = make_client([FakeResponse(text=EMPTY_FEED.format(total=0))])
    assert list(client.iter_pages(["cs.AI"], max_results=10, page_size=5)) == []


def test_persistent_empty_pages_stop_the_run_with_a_warning(caplog, monkeypatch):
    # The app loggers don't propagate to the root logger, so hook caplog in directly.
    monkeypatch.setattr(arxiv_client.logger, "handlers", [caplog.handler])
    client, session, _ = make_client([FakeResponse(text=EMPTY_FEED.format(total=500))] * 4)
    assert list(client.iter_pages(["cs.AI"], max_results=10, page_size=5)) == []
    assert len(session.calls) == 4
    assert "stopping early" in caplog.text
