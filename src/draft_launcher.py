"""Beginner-friendly menu for choosing an email workflow."""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import TextIO

from main import main


def run(
    *, input_fn: Callable[[str], str] = input, output: TextIO = sys.stdout,
) -> int:
    """Show a simple menu and run the selected workflow."""
    output.write(
        "\nChoose how you want to prepare your emails:\n"
        "1. Desktop app (recommended) - CV attached; use Thunderbird, Outlook, etc.\n"
        "2. Gmail in browser - opens your browser; attach the CV manually\n"
        "3. Automatic SMTP - sends only after you type SEND\n"
        "4. Exit\n\n"
    )
    choice = input_fn("Enter 1, 2, 3, or 4: ").strip()

    if choice == "1":
        return main(["--mode", "draft_only", "--all", "--refresh-drafts", "--open-drafts"])
    if choice == "2":
        return main(["--mode", "draft_only", "--all", "--refresh-drafts", "--browser-review"])
    if choice == "3":
        output.write("SMTP uses your private .env settings and sends at most 10 per day.\n")
        return main(["--mode", "send"])
    if choice == "4":
        output.write("Nothing created or sent.\n")
        return 0

    output.write("Invalid choice. Run the command again and enter 1, 2, 3, or 4.\n")
    return 2
