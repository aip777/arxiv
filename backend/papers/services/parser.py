"""
Parse arXiv Atom feeds into clean, flat records ready for the database.

The feed format is documented at https://info.arxiv.org/help/api/user-manual.html.
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from xml.etree.ElementTree import ParseError

from defusedxml import ElementTree

logger = logging.getLogger(__name__)

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "arxiv": "http://arxiv.org/schemas/atom",
    "opensearch": "http://a9.com/-/spec/opensearch/1.1/",
}

# Matches both new-style (2409.01234v2) and old-style (hep-th/9901001v1) ids.
ARXIV_ID_RE = re.compile(r"arxiv\.org/abs/(?P<id>.+?)(?:v(?P<version>\d+))?$")
WHITESPACE_RE = re.compile(r"\s+")
# Matches the column size for author names and DOIs.
MAX_NAME_LENGTH = 255


class FeedError(Exception):
    """The response is not a usable arXiv feed (bad XML or an API error entry)."""


@dataclass
class PaperRecord:
    arxiv_id: str
    version: int
    title: str
    abstract: str
    authors: list[str]
    primary_category: str
    categories: list[str]
    published: datetime
    updated: datetime
    doi: str | None = None
    journal_ref: str | None = None
    comment: str | None = None
    abs_url: str = ""
    pdf_url: str = ""
    content_hash: str = field(init=False)

    def __post_init__(self):
        self.content_hash = compute_content_hash(self.title, self.abstract)


@dataclass
class FeedPage:
    total_results: int
    records: list[PaperRecord]
    skipped: int = 0
    # Number of <entry> elements returned, including ones that failed to parse.
    entry_count: int = 0


def compute_content_hash(title: str, abstract: str) -> str:
    return hashlib.sha256(f"{title}\n\n{abstract}".encode()).hexdigest()


def clean_text(value: str | None) -> str:
    """Collapse the hard line wrapping arXiv puts in titles and abstracts."""
    if not value:
        return ""
    return WHITESPACE_RE.sub(" ", value).strip()


def optional_text(value: str | None, max_length: int | None = None) -> str | None:
    cleaned = clean_text(value)[:max_length]
    return cleaned or None


def parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def unique(values):
    """De-duplicate while keeping the original order (author order matters)."""
    seen = set()
    result = []
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def parse_feed(xml_text: str | bytes) -> FeedPage:
    try:
        root = ElementTree.fromstring(xml_text)
    except ParseError as exc:
        raise FeedError(f"Invalid XML from arXiv: {exc}") from exc

    entries = root.findall("atom:entry", NS)

    # arXiv reports query errors as a single entry whose id points at /api/errors.
    if len(entries) == 1:
        entry_id = entries[0].findtext("atom:id", default="", namespaces=NS)
        if "/api/errors" in entry_id:
            message = clean_text(entries[0].findtext("atom:summary", default="", namespaces=NS))
            raise FeedError(f"arXiv API error: {message or entry_id}")

    total_text = root.findtext("opensearch:totalResults", default="0", namespaces=NS)
    try:
        total_results = int(total_text)
    except ValueError:
        total_results = 0

    records = []
    skipped = 0
    for entry in entries:
        try:
            records.append(parse_entry(entry))
        except ValueError as exc:
            skipped += 1
            entry_id = entry.findtext("atom:id", default="?", namespaces=NS)
            logger.warning("Skipping malformed arXiv entry %s: %s", entry_id, exc)

    return FeedPage(
        total_results=total_results,
        records=records,
        skipped=skipped,
        entry_count=len(entries),
    )


def parse_entry(entry) -> PaperRecord:
    raw_id = clean_text(entry.findtext("atom:id", default="", namespaces=NS))
    match = ARXIV_ID_RE.search(raw_id)
    if not match:
        raise ValueError(f"unrecognised id {raw_id!r}")
    arxiv_id = match.group("id")
    version = int(match.group("version") or 1)

    title = clean_text(entry.findtext("atom:title", namespaces=NS))
    abstract = clean_text(entry.findtext("atom:summary", namespaces=NS))
    if not title or not abstract:
        raise ValueError("missing title or abstract")

    published = parse_datetime(entry.findtext("atom:published", namespaces=NS))
    if published is None:
        raise ValueError("missing or invalid published date")
    updated = parse_datetime(entry.findtext("atom:updated", namespaces=NS)) or published

    authors = unique(
        clean_text(author.findtext("atom:name", namespaces=NS))[:MAX_NAME_LENGTH]
        for author in entry.findall("atom:author", NS)
    )
    if not authors:
        raise ValueError("no authors")

    categories = unique(clean_text(category.get("term")) for category in entry.findall("atom:category", NS))
    primary_element = entry.find("arxiv:primary_category", NS)
    primary_category = clean_text(primary_element.get("term")) if primary_element is not None else ""
    if not primary_category:
        if not categories:
            raise ValueError("no categories")
        primary_category = categories[0]
    if primary_category.lower() not in {c.lower() for c in categories}:
        categories.insert(0, primary_category)

    abs_url = ""
    pdf_url = ""
    for link in entry.findall("atom:link", NS):
        if link.get("rel") == "alternate":
            abs_url = link.get("href", "")
        elif link.get("title") == "pdf":
            pdf_url = link.get("href", "")

    return PaperRecord(
        arxiv_id=arxiv_id,
        version=version,
        title=title,
        abstract=abstract,
        authors=authors,
        primary_category=primary_category,
        categories=categories,
        published=published,
        updated=updated,
        doi=optional_text(entry.findtext("arxiv:doi", namespaces=NS), max_length=MAX_NAME_LENGTH),
        journal_ref=optional_text(entry.findtext("arxiv:journal_ref", namespaces=NS)),
        comment=optional_text(entry.findtext("arxiv:comment", namespaces=NS)),
        abs_url=abs_url or f"https://arxiv.org/abs/{arxiv_id}v{version}",
        pdf_url=pdf_url,
    )
