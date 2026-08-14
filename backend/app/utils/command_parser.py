"""Chat command parser (Task 4.5).

Parses user chat input for known commands: /ask, /summarize, /remove, /lint,
/rebuild, /export. Bare messages (no / prefix) default to /ask.
"""

from __future__ import annotations

from dataclasses import dataclass

VALID_COMMANDS = ("ask", "summarize", "remove", "lint", "rebuild", "export")


@dataclass
class ParsedCommand:
    command: str
    args: str


def parse_command(text: str) -> ParsedCommand:
    """Parse chat input into a command + args.

    - ``/ask how does X work`` → ParsedCommand(command="ask", args="how does X work")
    - ``how does X work`` → ParsedCommand(command="ask", args="how does X work")
    - ``/rebuild`` → ParsedCommand(command="rebuild", args="")
    - ``/unknown`` → raises ValueError
    """
    text = text.strip()
    if not text:
        raise ValueError("Empty message")

    if not text.startswith("/"):
        return ParsedCommand(command="ask", args=text)

    parts = text[1:].split(None, 1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if command not in VALID_COMMANDS:
        raise ValueError(
            f"Unknown command '/{command}'. Valid commands: "
            + ", ".join(f"/{c}" for c in VALID_COMMANDS)
        )

    return ParsedCommand(command=command, args=args)
