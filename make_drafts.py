"""Beginner-friendly entry point: create all safe local drafts and open their review page."""

from __future__ import annotations

from main import main


def run() -> int:
    """Create all eligible local drafts and open their private review page."""
    return main(["--mode", "draft_only", "--all", "--open-drafts"])


if __name__ == "__main__":
    raise SystemExit(run())
