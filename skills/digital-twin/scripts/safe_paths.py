from __future__ import annotations

from pathlib import Path


def is_safe_input_file(path: str | Path, root: Path) -> bool:
    """Return True for regular, non-symlink files contained by root."""
    candidate = Path(path)
    try:
        if candidate.is_symlink() or not candidate.is_file():
            return False
        candidate.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False
