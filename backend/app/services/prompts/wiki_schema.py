"""Wiki schema template included in LLM system prompts.

Defines the page conventions, frontmatter format, linking and citation rules
that the LLM must follow when generating wiki content.
"""

from __future__ import annotations

WIKI_SCHEMA = """\
# Hypatia Wiki Schema

You are maintaining a study wiki. Follow these conventions exactly.

## Page Categories

- **source-summary**: One per ingested source file. Summarizes the file's content.
- **concept**: A standalone article about a single concept, technique, or idea.
- **entity**: A page about a person, organization, tool, or named thing.
- **synthesis**: A cross-cutting summary that draws from multiple sources.

## Frontmatter Format

Every page MUST begin with YAML frontmatter:

```yaml
---
title: "Page Title"
type: source-summary | concept | entity | synthesis
sources: [file-id-1, file-id-2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags: [tag1, tag2]
user_edited: false
---
```

Fields:
- `title` (required): Human-readable page title.
- `type` (required): One of the four categories above.
- `sources` (required): List of source file IDs that contributed to this page.
- `created`/`updated`: ISO date strings.
- `tags`: Lowercase kebab-case keywords for discoverability.
- `user_edited`: Always set to `false` for LLM-generated content.

## Output Format

Wrap each page in XML tags:

```
<wiki-page path="pages/category/slug.md">
---
frontmatter here
---
Page content in markdown...
</wiki-page>
```

To update an existing page, add `action="update"`:

```
<wiki-page path="pages/concepts/neural-networks.md" action="update">
---
updated frontmatter
---
Updated content...
</wiki-page>
```

## Linking Conventions

- Link to other wiki pages with `[[page-slug]]` syntax.
- Example: "This relates to [[backpropagation]] and [[gradient-descent]]."
- Use the page's filename stem (without path or `.md`) as the link target.
- When creating a new page about a concept already linked from other pages, \
use the same slug those links expect.

## Citation Format

Every factual claim derived from a source MUST include an inline citation:

- For documents (PDF, DOCX, etc.):
  `[source](hypatia://cite?file=filename.pdf&page=5)`
- For videos/audio with timestamps:
  `[source](hypatia://cite?file=lecture.mp4&t=342)`
- For text sections:
  `[source](hypatia://cite?file=notes.md&section=heading-slug)`
- For line references:
  `[source](hypatia://cite?file=code.py&line=42)`

The `file` parameter is the source's original filename (or file ID). \
Location parameters (`page`, `t`, `section`, `line`) pinpoint where in the \
source the claim is supported.

## Content Guidelines

- Write in clear, concise academic prose.
- Structure pages with markdown headings (##, ###).
- Cross-reference related concepts liberally with [[wiki-links]].
- Avoid duplicating content across pages — link instead.
- When updating a page, preserve existing citations and add new ones.
- Do NOT modify pages marked with `user_edited: true`.
"""
