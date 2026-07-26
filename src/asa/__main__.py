"""Enable ``python -m asa`` by delegating to the CLI entry point."""

from asa.cli import main

raise SystemExit(main())
