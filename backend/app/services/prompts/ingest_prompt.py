"""System prompt for source ingestion (Task 3B.9)."""

from __future__ import annotations

from .wiki_schema import WIKI_SCHEMA

INGEST_SYSTEM_PROMPT = f"""\
{WIKI_SCHEMA}

## Your Task

You are ingesting a source document into the wiki. You must:

1. Create a **source-summary** page summarizing the document.
2. Identify key **concepts** and **entities** mentioned in the source.
3. For each concept/entity: create a new page OR update an existing one \
(use action="update" if the page already exists in the index).
4. Include citations linking claims back to the source using the \
hypatia://cite format described above.
5. Add cross-references between pages using [[wiki-links]].

Output ONLY <wiki-page> tags. No other text before or after.
"""
