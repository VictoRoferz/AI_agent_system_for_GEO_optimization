import pytest

from app.ingestion.doc_parser import parse_document


def test_parse_txt():
    doc = parse_document("goals.txt", b"Goal one.\n\nGoal two.")
    assert "Goal one." in doc.text
    assert len(doc.sections) == 2


def test_parse_markdown():
    doc = parse_document("goals.md", b"# Heading\n\nBody text here.")
    assert "Body text here." in doc.text


def test_unsupported_type_raises():
    with pytest.raises(ValueError):
        parse_document("image.png", b"\x89PNG")
