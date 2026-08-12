"""Citation URI generation and parsing for wiki pages.

Citations use a ``hypatia://`` URI scheme that the frontend resolves to
navigate to the original source location (PDF page, video timestamp, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse

_VALID_LOCATION_TYPES = {"page", "section", "line", "t"}


@dataclass
class CitationRef:
    """A parsed citation reference pointing to a source location."""

    file_id: str
    location_type: str | None = None
    location_value: str | None = None


def generate_citation_uri(
    file_id: str,
    location_type: str | None = None,
    location_value: str | None = None,
) -> str:
    """Create a ``hypatia://cite`` URI for embedding in wiki markdown.

    Examples:
        >>> generate_citation_uri("chapter-3-notes.pdf", "page", "5")
        'hypatia://cite?file=chapter-3-notes.pdf&page=5'
        >>> generate_citation_uri("lecture-1.mp4", "t", "342")
        'hypatia://cite?file=lecture-1.mp4&t=342'
    """
    params: dict[str, str] = {"file": file_id}
    if location_type and location_value:
        if location_type not in _VALID_LOCATION_TYPES:
            raise ValueError(
                f"Invalid location_type={location_type!r}. Valid: {sorted(_VALID_LOCATION_TYPES)}"
            )
        params[location_type] = location_value
    return f"hypatia://cite?{urlencode(params)}"


def parse_citation_uri(uri: str) -> CitationRef | None:
    """Parse a ``hypatia://cite`` URI back into its components.

    Returns None if the URI is not a valid hypatia citation.
    """
    parsed = urlparse(uri)
    if parsed.scheme != "hypatia" or parsed.netloc != "cite":
        return None

    params = parse_qs(parsed.query)
    file_ids = params.get("file")
    if not file_ids:
        return None

    file_id = file_ids[0]
    location_type: str | None = None
    location_value: str | None = None

    for loc_type in _VALID_LOCATION_TYPES:
        values = params.get(loc_type)
        if values:
            location_type = loc_type
            location_value = values[0]
            break

    return CitationRef(
        file_id=file_id,
        location_type=location_type,
        location_value=location_value,
    )
