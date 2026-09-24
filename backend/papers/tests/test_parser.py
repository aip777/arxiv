from datetime import UTC, datetime

import pytest

from papers.services.parser import FeedError, compute_content_hash, parse_feed


def test_parses_entries_into_clean_records(atom_feed):
    page = parse_feed(atom_feed)

    assert page.total_results == 3
    assert page.entry_count == 3
    assert page.skipped == 1
    assert len(page.records) == 2

    paper = page.records[0]
    assert paper.arxiv_id == "2409.01234"
    assert paper.version == 2
    assert paper.title == "Graph Neural Networks for Molecular Property Prediction"
    assert paper.abstract == (
        "We propose a graph neural network that predicts molecular properties. "
        "Experiments show strong results on standard benchmarks."
    )
    assert paper.published == datetime(2024, 9, 2, 10, 15, tzinfo=UTC)
    assert paper.updated == datetime(2024, 9, 5, 17, 59, 59, tzinfo=UTC)
    assert paper.doi == "10.1000/xyz123"
    assert paper.journal_ref == "Journal of Chemical AI 3 (2024) 1-12"
    assert paper.comment == "12 pages, 4 figures"
    assert paper.abs_url == "http://arxiv.org/abs/2409.01234v2"
    assert paper.pdf_url == "http://arxiv.org/pdf/2409.01234v2"
    assert paper.content_hash == compute_content_hash(paper.title, paper.abstract)


def test_authors_are_normalised_and_deduplicated_in_order(atom_feed):
    paper = parse_feed(atom_feed).records[0]
    assert paper.authors == ["Alice Smith", "Bob Jones"]


def test_categories_keep_primary_first_and_include_cross_lists(atom_feed):
    paper = parse_feed(atom_feed).records[0]
    assert paper.primary_category == "cs.LG"
    assert paper.categories == ["cs.LG", "cs.AI", "q-bio.QM"]


def test_missing_doi_and_journal_ref_become_none(atom_feed):
    old_paper = parse_feed(atom_feed).records[1]
    assert old_paper.doi is None
    assert old_paper.journal_ref is None
    assert old_paper.comment is None


def test_old_style_ids_and_missing_primary_in_categories(atom_feed):
    old_paper = parse_feed(atom_feed).records[1]
    assert old_paper.arxiv_id == "hep-th/9901001"
    assert old_paper.version == 1
    # The primary category is added to the category list when the feed omits it there.
    assert old_paper.categories == ["cs.CL", "stat.ML"]


def test_invalid_xml_raises_feed_error():
    with pytest.raises(FeedError):
        parse_feed("<feed><entry>")


def test_api_error_entry_raises_feed_error():
    error_feed = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/api/errors#incorrect_id_format_for_1234</id>
        <title>Error</title>
        <summary>incorrect id format for 1234</summary>
      </entry>
    </feed>"""
    with pytest.raises(FeedError, match="incorrect id format"):
        parse_feed(error_feed)


def test_empty_feed_returns_no_records():
    empty = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">
      <opensearch:totalResults>0</opensearch:totalResults>
    </feed>"""
    page = parse_feed(empty)
    assert page.total_results == 0
    assert page.records == []
