"""Beginner-friendly orchestration for creating all local drafts."""

from __future__ import annotations

from main import main


def run() -> int:
    """Create all eligible local drafts and open their private review page."""
    return main(["--mode", "draft_only", "--all", "--open-drafts"])
