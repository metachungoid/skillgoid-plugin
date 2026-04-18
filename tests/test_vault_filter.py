"""Tests for scripts/vault_filter.py — filter vault lessons by Status: resolved in vX.Y."""
from scripts.vault_filter import (
    filter_lessons,
    parse_lessons,
    parse_version,
)


SAMPLE = """# python lessons

<!-- curated by Skillgoid retrospect — edit with care -->

## Lesson A

Current advice.

Last touched: 2026-04-17 by project "jyctl"

## Lesson B (resolved)

Old advice superseded.

Status: resolved in v0.4
Last touched: 2026-04-18 by project "taskq"

## Lesson C

More current advice.

Last touched: 2026-04-18 by project "mdstats"
"""


class TestParseVersion:
    def test_plain_version(self):
        assert parse_version("0.4") == (0, 4)

    def test_with_v_prefix(self):
        assert parse_version("v0.4") == (0, 4)

    def test_three_segments(self):
        assert parse_version("0.4.2") == (0, 4, 2)

    def test_invalid_returns_none(self):
        assert parse_version("not a version") is None


class TestParseLessons:
    def test_split_by_h2_headings(self):
        lessons = parse_lessons(SAMPLE)
        assert len(lessons) == 3
        assert lessons[0]["title"] == "Lesson A"
        assert lessons[1]["title"] == "Lesson B (resolved)"
        assert lessons[2]["title"] == "Lesson C"

    def test_extracts_status_line(self):
        lessons = parse_lessons(SAMPLE)
        assert lessons[1]["resolved_in"] == (0, 4)
        assert lessons[0]["resolved_in"] is None
        assert lessons[2]["resolved_in"] is None

    def test_preamble_is_separate(self):
        """The H1 title + HTML comment before the first H2 is preserved as preamble."""
        lessons = parse_lessons(SAMPLE)
        # The preamble is not itself a lesson
        titles = [line["title"] for line in lessons]
        assert "python lessons" not in titles


class TestFilterLessons:
    def test_newer_plugin_suppresses_resolved(self):
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=(0, 4))
        assert [line["title"] for line in active] == ["Lesson A", "Lesson C"]
        assert [line["title"] for line in resolved] == ["Lesson B (resolved)"]

    def test_equal_version_suppresses_resolved(self):
        """If lesson is 'resolved in v0.4' and we're running v0.4, hide it."""
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=(0, 4))
        assert any(line["title"] == "Lesson B (resolved)" for line in resolved)

    def test_older_plugin_keeps_resolved_active(self):
        """Running v0.3 plugin against a lesson marked 'resolved in v0.4':
        the resolution isn't here yet, so the lesson still applies."""
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=(0, 3))
        active_titles = {line["title"] for line in active}
        assert "Lesson B (resolved)" in active_titles
        assert resolved == []

    def test_none_version_keeps_everything_active(self):
        """If plugin version can't be read, fail-open: don't filter."""
        lessons = parse_lessons(SAMPLE)
        active, resolved = filter_lessons(lessons, current_version=None)
        assert len(active) == 3
        assert resolved == []

    def test_malformed_status_line_treated_as_unresolved(self):
        text = "## Broken\n\nadvice\n\nStatus: not a real format\n"
        lessons = parse_lessons(text)
        assert lessons[0]["resolved_in"] is None
