"""Tests for the wiki parser (Task 3A.4)."""

from __future__ import annotations

import pytest

from app.services.wiki_parser import normalize_page_path, parse_llm_output

SAMPLE_OUTPUT = """\
<wiki-page path="pages/source-summaries/lecture-1.md">
---
title: "Lecture 1: Intro to Neural Networks"
type: source-summary
sources: [file-id-1]
tags: [neural-networks, introduction]
user_edited: false
---
# Lecture 1 Summary

Neural networks are computing systems inspired by biological brains.
They consist of layers of interconnected nodes.
</wiki-page>

<wiki-page path="pages/concepts/backpropagation.md" action="update">
---
title: "Backpropagation"
type: concept
sources: [file-id-1, file-id-2]
tags: [training, optimization]
---
## What is Backpropagation?

Backpropagation computes gradients of the loss function.
</wiki-page>

<wiki-page path="pages/entities/geoffrey-hinton.md">
---
title: "Geoffrey Hinton"
type: entity
sources: [file-id-1]
tags: [researcher, deep-learning]
---
Geoffrey Hinton is a pioneer in deep learning.
</wiki-page>
"""


def test_parse_valid_output():
    pages = parse_llm_output(SAMPLE_OUTPUT)
    assert len(pages) == 3


def test_page_fields():
    pages = parse_llm_output(SAMPLE_OUTPUT)
    p = pages[0]
    assert p.path == "pages/source-summaries/lecture-1.md"
    assert p.title == "Lecture 1: Intro to Neural Networks"
    assert p.category == "source-summary"
    assert p.sources == ["file-id-1"]
    assert p.tags == ["neural-networks", "introduction"]
    assert p.action == "create"
    assert p.user_edited is False


def test_action_attribute():
    pages = parse_llm_output(SAMPLE_OUTPUT)
    assert pages[1].action == "update"
    assert pages[0].action == "create"


def test_multiple_sources():
    pages = parse_llm_output(SAMPLE_OUTPUT)
    assert pages[1].sources == ["file-id-1", "file-id-2"]


def test_empty_input():
    pages = parse_llm_output("")
    assert pages == []


def test_no_wiki_pages_in_output():
    pages = parse_llm_output("Just some random text without any wiki-page tags.")
    assert pages == []


def test_missing_frontmatter_skipped():
    raw = """\
<wiki-page path="pages/concepts/no-fm.md">
Just content without frontmatter
</wiki-page>
"""
    pages = parse_llm_output(raw)
    assert pages == []


def test_missing_title_skipped():
    raw = """\
<wiki-page path="pages/concepts/no-title.md">
---
type: concept
sources: [x]
tags: [y]
---
Content here.
</wiki-page>
"""
    pages = parse_llm_output(raw)
    assert pages == []


def test_invalid_category_defaults():
    raw = """\
<wiki-page path="pages/concepts/bad-cat.md">
---
title: "Test Page"
type: invalid-category
sources: [x]
tags: [y]
---
Content here.
</wiki-page>
"""
    pages = parse_llm_output(raw)
    assert len(pages) == 1
    assert pages[0].category == "concept"


def test_user_edited_flag():
    raw = """\
<wiki-page path="pages/concepts/edited.md">
---
title: "User Edited Page"
type: concept
sources: [x]
user_edited: true
---
Content.
</wiki-page>
"""
    pages = parse_llm_output(raw)
    assert pages[0].user_edited is True


@pytest.mark.parametrize(
    "path",
    [
        "../../settings.json",
        "pages/../../.credentials.md",
        "/etc/passwd.md",
        "C:/Users/x/evil.md",
        "pages/.git/hooks/pre-commit.md",
        "pages/.GIT./config.md",
        "pages/x:stream.md",
        "pages/notes.txt",
        "index.md",
        "pages//double.md",
    ],
)
def test_unsafe_page_paths_rejected(path: str):
    assert normalize_page_path(path) is None


def test_page_path_normalized():
    assert normalize_page_path(r"./pages\concepts\x.md") == "pages/concepts/x.md"
    assert normalize_page_path("index.md", require_pages_dir=False) == "index.md"


def test_unsafe_llm_page_path_skipped():
    raw = """\
<wiki-page path="../../settings.json">
---
title: "Evil"
type: concept
---
{}
</wiki-page>
<wiki-page path="pages/concepts/ok.md">
---
title: "Ok"
type: concept
---
Fine.
</wiki-page>
"""
    pages = parse_llm_output(raw)
    assert [p.path for p in pages] == ["pages/concepts/ok.md"]
