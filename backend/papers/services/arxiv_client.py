"""
Minimal, polite client for the arXiv query API.

arXiv asks clients to wait at least 3 seconds between requests. When it is
unhappy it answers with 429/503, and sometimes with 406 from its CDN, so those
are retried with exponential backoff.
"""

import logging
import re
import time
from collections.abc import Iterator

import requests
from django.conf import settings

from papers.services.parser import FeedError, FeedPage, parse_feed

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {406, 429, 500, 502, 503, 504}
USER_AGENT = "arxiv-rag-ingest/1.0"
# arXiv occasionally returns an empty page mid-way through a result set; a retry usually fixes it.
EMPTY_PAGE_RETRIES = 3
# e.g. cs.AI, stat.ML, hep-th, astro-ph.CO
CATEGORY_RE = re.compile(r"^[a-z-]+(\.[A-Za-z-]+)?$")


class ArxivClientError(Exception):
    pass


def build_category_query(categories: list[str]) -> str:
    categories = [c.strip() for c in categories if c and c.strip()]
    if not categories:
        raise ValueError("At least one category is required.")
    invalid = [c for c in categories if not CATEGORY_RE.match(c)]
    if invalid:
        raise ValueError(f"Invalid arXiv category: {', '.join(invalid)}")
    return " OR ".join(f"cat:{category}" for category in categories)


class ArxivClient:
    def __init__(
        self,
        base_url=None,
        delay=None,
        max_retries=None,
        timeout=None,
        session=None,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.base_url = base_url or settings.ARXIV_API_URL
        self.delay = settings.ARXIV_REQUEST_DELAY if delay is None else delay
        self.max_retries = settings.ARXIV_MAX_RETRIES if max_retries is None else max_retries
        self.timeout = timeout or settings.ARXIV_TIMEOUT
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        # Injected so tests do not actually wait.
        self._sleep = sleep
        self._clock = clock
        self._last_request_at = None

    def _throttle(self):
        if self._last_request_at is None:
            return
        wait = self.delay - (self._clock() - self._last_request_at)
        if wait > 0:
            self._sleep(wait)

    def _get(self, params: dict) -> str:
        for attempt in range(self.max_retries + 1):
            self._throttle()
            self._last_request_at = self._clock()
            try:
                response = self.session.get(self.base_url, params=params, timeout=self.timeout)
            except requests.RequestException as exc:
                logger.debug("arXiv request error: %s", exc)
                error = f"network error: {type(exc).__name__}"
            else:
                if response.status_code == 200:
                    return response.text
                if response.status_code not in RETRYABLE_STATUS:
                    raise ArxivClientError(f"arXiv returned HTTP {response.status_code}: {response.text[:200]}")
                error = f"HTTP {response.status_code}"

            if attempt == self.max_retries:
                raise ArxivClientError(f"arXiv request failed after {attempt + 1} attempts ({error})")
            backoff = self.delay * (2**attempt)
            logger.warning(
                "arXiv request failed (%s); retrying in %.0fs (attempt %d/%d)",
                error,
                backoff,
                attempt + 1,
                self.max_retries,
            )
            self._sleep(backoff)

    def fetch_page(self, query: str, start: int, max_results: int) -> FeedPage:
        # Newest updates first, so new and revised papers are always at the front.
        params = {
            "search_query": query,
            "start": start,
            "max_results": max_results,
            "sortBy": "lastUpdatedDate",
            "sortOrder": "descending",
        }
        try:
            return parse_feed(self._get(params))
        except FeedError as exc:
            raise ArxivClientError(str(exc)) from exc

    def iter_pages(self, categories: list[str], max_results: int, page_size: int) -> Iterator[FeedPage]:
        """
        Yield pages of results, newest updates first, until `max_results` entries
        have been requested or arXiv runs out of results.
        """
        query = build_category_query(categories)
        start = 0
        total = None
        while start < max_results and (total is None or start < total):
            size = min(page_size, max_results - start)
            page = self.fetch_page(query, start, size)

            retries = 0
            while page.entry_count == 0 and start < page.total_results and retries < EMPTY_PAGE_RETRIES:
                retries += 1
                logger.warning(
                    "arXiv returned an empty page at start=%d; retrying (%d/%d)", start, retries, EMPTY_PAGE_RETRIES
                )
                page = self.fetch_page(query, start, size)

            total = page.total_results
            if page.entry_count == 0:
                if start < total:
                    logger.warning(
                        "arXiv kept returning empty pages at start=%d although it reports %d results; stopping early",
                        start,
                        total,
                    )
                else:
                    logger.info("No more results from arXiv at start=%d (total=%d)", start, total)
                return

            logger.info("Fetched %d entries (start=%d, total available=%d)", page.entry_count, start, total)
            yield page
            start += page.entry_count
