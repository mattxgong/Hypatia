"""LLM prompt constants for the wiki engine."""

from app.services.prompts.ingest_prompt import INGEST_SYSTEM_PROMPT
from app.services.prompts.lint_prompt import LINT_SYSTEM_PROMPT
from app.services.prompts.query_prompt import ASK_SYSTEM_PROMPT
from app.services.prompts.summarize_prompt import SUMMARIZE_SYSTEM_PROMPT
from app.services.prompts.wiki_schema import WIKI_SCHEMA

__all__ = [
    "ASK_SYSTEM_PROMPT",
    "INGEST_SYSTEM_PROMPT",
    "LINT_SYSTEM_PROMPT",
    "SUMMARIZE_SYSTEM_PROMPT",
    "WIKI_SCHEMA",
]
