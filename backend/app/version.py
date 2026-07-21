"""Deployment build information (Mission M003, Gate G3 review follow-up).

The monitor header must make it immediately obvious *which* software is
running on the host during troubleshooting (supervisor review, PR 2):
Observatory version, git commit, and the active mission. The version comes
from :class:`app.config.Settings`; this module supplies the git commit.

Detection is standard-library only and read-only:

1. the ``GIT_COMMIT`` environment variable wins — set it in deployments
   that do not run from a git checkout (e.g. container image builds where
   the SHA is stamped at build time);
2. otherwise the ``.git`` directory found by walking up from this file is
   read directly (``HEAD`` → ref file or ``packed-refs``) — no ``git``
   binary, no subprocess;
3. if neither yields a commit the value is ``None`` and the monitor renders
   an honest ``unknown`` rather than guessing.

The commit of a running server cannot change (a redeploy restarts the
process), so it is detected once at import time.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

_HEAD_REF_PREFIX = "ref: "
_GITDIR_PREFIX = "gitdir:"


def _resolve_ref(git_dir: Path, ref: str) -> str | None:
    """Resolve a symbolic ref to a commit SHA (loose file or packed-refs)."""
    ref_file = git_dir / ref
    try:
        if ref_file.is_file():
            value = ref_file.read_text(encoding="utf-8").strip()
            return value or None
        packed = git_dir / "packed-refs"
        if packed.is_file():
            for line in packed.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith(("#", "^")):
                    continue
                sha, _, name = line.partition(" ")
                if name.strip() == ref:
                    return sha or None
    except OSError:
        return None
    return None


def detect_git_commit(start: Path | None = None) -> str | None:
    """Best-effort commit SHA of the running checkout (never raises).

    ``start`` overrides the walk origin for tests; production always starts
    from this module's own location inside the deployed tree.
    """
    env = os.environ.get("GIT_COMMIT", "").strip()
    if env:
        return env
    origin = (start or Path(__file__)).resolve()
    origin = origin if origin.is_dir() else origin.parent
    for candidate in (origin, *origin.parents):
        git_dir = candidate / ".git"
        try:
            if git_dir.is_file():
                # Worktree / submodule: `.git` is a pointer file.
                content = git_dir.read_text(encoding="utf-8").strip()
                if not content.startswith(_GITDIR_PREFIX):
                    return None
                git_dir = (candidate / content[len(_GITDIR_PREFIX) :].strip()).resolve()
            if not git_dir.is_dir():
                continue
            head_file = git_dir / "HEAD"
            if not head_file.is_file():
                return None
            head = head_file.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if head.startswith(_HEAD_REF_PREFIX):
            return _resolve_ref(git_dir, head[len(_HEAD_REF_PREFIX) :].strip())
        return head or None  # detached HEAD stores the SHA directly
    return None


#: Detected once at import — the checkout under a running server is fixed.
GIT_COMMIT: str | None = detect_git_commit()


def detect_build_timestamp() -> str | None:
    """Best-effort build timestamp for the monitor (M003.5 §6). Never raises.

    There is no build pipeline stamping artifacts yet (deployments run from
    a git checkout), so "build timestamp" is defined as *the committer
    timestamp of the deployed commit* — verifiable, reproducible, and
    matching what "which build is this?" actually asks. Resolution order
    (judgment call, docs/M003.5-notes.md):

    1. the ``BUILD_TIMESTAMP`` environment variable wins — set it in
       packaged/container deployments where a real build step exists;
    2. otherwise ``git log -1 --format=%cI`` runs **once at import** (the
       checkout under a running server is fixed). This is the one deliberate
       subprocess exception to the no-subprocess rule above: commit
       timestamps live in packfiles, which stdlib-only parsing cannot read
       economically;
    3. if neither yields a value the monitor renders an honest ``unknown``.
    """
    env = os.environ.get("BUILD_TIMESTAMP", "").strip()
    if env:
        return env
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            capture_output=True,
            text=True,
            timeout=5.0,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


#: Detected once at import, like :data:`GIT_COMMIT`.
BUILD_TIMESTAMP: str | None = detect_build_timestamp()
