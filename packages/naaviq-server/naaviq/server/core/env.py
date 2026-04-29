"""
Locate the .env file for this workspace.

Walks up from any file in the repo until it finds the workspace root —
identified by having both a pyproject.toml and a packages/ directory.
This avoids fragile parent-index counting (parents[3], parents[5], etc.)
that breaks whenever files are moved.
"""

from pathlib import Path


def find_workspace_root(start: Path | None = None) -> Path:
    """
    Walk up the directory tree from `start` until the uv workspace root is found.

    The workspace root is the directory that contains both:
      - pyproject.toml  (the uv workspace manifest)
      - packages/       (the monorepo packages directory)

    Args:
        start: Starting directory. Defaults to the directory of this file.

    Raises:
        FileNotFoundError: If no workspace root is found before hitting the filesystem root.
    """
    current = (start or Path(__file__).parent).resolve()
    while current != current.parent:
        if (current / "pyproject.toml").exists() and (current / "packages").exists():
            return current
        current = current.parent
    raise FileNotFoundError(
        "Could not find workspace root. "
        "Expected a directory with pyproject.toml and packages/ — "
        "are you running from inside the Naaviq monorepo?"
    )


#: Absolute path to the workspace root .env file.
#: All config classes should use this instead of counting parent indices.
ENV_FILE = find_workspace_root() / ".env"
