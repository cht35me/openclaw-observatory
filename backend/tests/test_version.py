"""Git-commit detection for the /monitor deployment header (Gate G3 review).

``detect_git_commit`` is stdlib-only, read-only, and must never raise: the
monitor renders ``unknown`` when no commit is available, it does not guess.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.version import detect_git_commit

SHA = "a" * 40
OTHER_SHA = "b" * 40


def _make_checkout(root: Path, *, packed: bool = False, detached: bool = False) -> Path:
    """Fabricate a minimal .git layout under ``root``; return a nested dir."""
    git = root / ".git"
    git.mkdir()
    if detached:
        (git / "HEAD").write_text(f"{SHA}\n", encoding="utf-8")
    else:
        (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        if packed:
            (git / "packed-refs").write_text(
                "# pack-refs with: peeled fully-peeled sorted\n"
                f"{OTHER_SHA} refs/heads/other\n"
                f"{SHA} refs/heads/main\n"
                f"^{OTHER_SHA}\n",
                encoding="utf-8",
            )
        else:
            ref = git / "refs" / "heads"
            ref.mkdir(parents=True)
            (ref / "main").write_text(f"{SHA}\n", encoding="utf-8")
    nested = root / "backend" / "app"
    nested.mkdir(parents=True)
    return nested


def test_env_variable_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GIT_COMMIT", "deadbeef")
    assert detect_git_commit(tmp_path) == "deadbeef"


def test_loose_ref_resolved_walking_up(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    nested = _make_checkout(tmp_path)
    assert detect_git_commit(nested) == SHA


def test_packed_ref_resolved(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    nested = _make_checkout(tmp_path, packed=True)
    assert detect_git_commit(nested) == SHA


def test_detached_head_returns_sha_directly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    nested = _make_checkout(tmp_path, detached=True)
    assert detect_git_commit(nested) == SHA


def test_no_checkout_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    assert detect_git_commit(tmp_path) is None


def test_real_repository_detected(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test suite itself runs inside the Observatory checkout."""
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    commit = detect_git_commit(Path(__file__))
    assert commit is not None
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
