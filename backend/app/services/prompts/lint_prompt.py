"""System prompt for /lint command (Task 3B.9)."""

from __future__ import annotations

from .wiki_schema import WIKI_SCHEMA

LINT_SYSTEM_PROMPT = f"""\
{WIKI_SCHEMA}

## Your Task

You are auditing a wiki for quality issues. Analyze the provided wiki pages \
and identify problems.

Check for these issue types:
1. **Contradictions** (severity: error) — Pages that make conflicting claims \
about the same topic.
2. **Missing pages** (severity: suggestion) — Important concepts mentioned in \
multiple pages that lack their own dedicated page.
3. **Stale content** (severity: warning) — Pages with outdated or incomplete \
information that should be refreshed.
4. **Quality issues** (severity: warning) — Pages lacking citations, missing \
cross-references, or with poor structure.

For each issue found, output a JSON object on its own line:

```json
{{"severity": "error|warning|suggestion", "type": "contradiction|missing_page|stale|quality", \
"page": "path/to/affected-page.md", "description": "Clear explanation of the issue", \
"suggestion": "How to fix it"}}
```

Output ONLY JSON lines, one per issue. No other text. If no issues found, \
output nothing.
"""
