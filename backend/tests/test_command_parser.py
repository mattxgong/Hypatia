"""Tests for command parser (Task 4.5)."""

from __future__ import annotations

import pytest

from app.utils.command_parser import ParsedCommand, parse_command


class TestParseCommand:
    def test_bare_message_defaults_to_ask(self) -> None:
        result = parse_command("how does photosynthesis work")
        assert result == ParsedCommand(command="ask", args="how does photosynthesis work")

    def test_explicit_ask(self) -> None:
        result = parse_command("/ask what is ATP")
        assert result == ParsedCommand(command="ask", args="what is ATP")

    def test_summarize_command(self) -> None:
        result = parse_command("/summarize lecture1.pdf")
        assert result == ParsedCommand(command="summarize", args="lecture1.pdf")

    def test_remove_command(self) -> None:
        result = parse_command("/remove lecture1.pdf")
        assert result == ParsedCommand(command="remove", args="lecture1.pdf")

    def test_lint_no_args(self) -> None:
        result = parse_command("/lint")
        assert result == ParsedCommand(command="lint", args="")

    def test_rebuild_no_args(self) -> None:
        result = parse_command("/rebuild")
        assert result == ParsedCommand(command="rebuild", args="")

    def test_export_no_args(self) -> None:
        result = parse_command("/export")
        assert result == ParsedCommand(command="export", args="")

    def test_command_case_insensitive(self) -> None:
        result = parse_command("/ASK what is this")
        assert result.command == "ask"

    def test_unknown_command_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown command '/foo'"):
            parse_command("/foo bar")

    def test_empty_message_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty message"):
            parse_command("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="Empty message"):
            parse_command("   ")

    def test_leading_whitespace_stripped(self) -> None:
        result = parse_command("  /summarize notes.md  ")
        assert result == ParsedCommand(command="summarize", args="notes.md")
