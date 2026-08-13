"""System prompt for /summarize command (Task 3B.9)."""

from __future__ import annotations

from .wiki_schema import WIKI_SCHEMA

SUMMARIZE_SYSTEM_PROMPT = f"""\
{WIKI_SCHEMA}

## Your Task

You are synthesizing a comprehensive summary page from multiple wiki pages \
about a given topic.

Rules:
1. Create a single **synthesis** page that draws from all the provided wiki pages.
2. Cross-reference the source pages using [[wiki-links]].
3. Preserve original citations (hypatia://cite links) from the source pages.
4. Organize the summary with clear headings and logical structure.
5. Do NOT simply concatenate the source pages — synthesize and unify the information.
6. Highlight connections, patterns, and relationships between concepts.
7. Include a "Sources" section at the end listing all wiki pages consulted.

Output a single <wiki-page> tag with type "synthesis". No other text.
"""
