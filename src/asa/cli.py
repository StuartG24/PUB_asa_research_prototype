"""Command-line entry point for asa.

Wired up two ways:
- as the ``asa`` console script (see ``[project.scripts]`` in pyproject.toml);
- via ``python -m asa`` (see ``__main__.py``).

So:
- uv run asa
- uv run python -m asa
"""

from asa.greeter import Greeter


def main() -> None:
    """Print the greeting."""
    print(Greeter().greet())
