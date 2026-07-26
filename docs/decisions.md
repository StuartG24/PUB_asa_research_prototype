# Design decisions

Why `asa-research-prototype` is built the way it is — the reasoning behind the choices, kept
separate from the description of the code itself. [Architecture](architecture.md) covers *what*
the pieces are and how they fit; this document covers *why*.

Entries are append-only and numbered: a decision that is superseded gets a note, not a rewrite,
so the record of what was thought at the time survives.

Decision 1 covers the scaffold. It is deliberately compact — most of the positive choices below
are also documented at the point of use, in `pyproject.toml` comments and the
[README](../README.md), and are summarised here only so the whole picture sits in one place. The
*Considered and rejected* section is the part with no other home: a road not taken leaves no line
of code to attach a comment to.

Relative links below are written from the repository root.

---

## 1. Scaffold and tooling

- **Packaged uv project** — it has a `[build-system]` (`uv_build`, `src/` layout), so `uv sync`
  builds and installs it into `.venv` in editable mode. That install is what makes `import asa`
  resolve from tests, notebooks and the console script alike, with no `sys.path` manipulation.
  Consequently `[tool.pytest.ini_options]` sets **no `pythonpath`** — the sibling project
  `dev-conv-agent` needs `pythonpath = ["."]` precisely because it is *not* packaged.

- **Three names, deliberately different** — repository `asa_research_prototype`, distribution
  `asa-research-prototype`, import `asa`. The short import comes from
  `[tool.uv.build-backend] module-name`, overriding uv's default of deriving the module directory
  from the project name. Without it the import would be `asa_research_prototype`.

- **No runtime dependencies** — `dependencies = []` is a decision, not an oversight. Dependencies
  arrive when real code needs them, via `uv add`.

- **Both entry points kept** — the `asa` console script and `python -m asa` do the same thing but
  prove different things. The console script exercises the whole packaging path; `python -m asa`
  bypasses it and tests only that the package imports. If packaging broke, the first would fail
  and the second would still pass, which makes the pair a useful diagnostic.

- **ruff** as linter and import-sorter, enforced by [`tests/test_lint.py`](../tests/test_lint.py)
  so `uv run pytest` is also the lint gate; **autopep8** as the formatter, because it enforces
  PEP 8 while leaving hand-arranged signatures alone where `ruff format` re-stacks parameters
  all-or-nothing. `[tool.ruff] line-length` and `[tool.autopep8] max_line_length` are mirrored at
  120 so the two can never disagree.

- **Pylance set to `standard`** in [`.vscode/settings.json`](../.vscode/settings.json),
  overriding a stricter global setting. Strict flags "unknown type" on every under-typed
  dependency — and robotics and ML libraries are routinely under-typed — which trains you to
  ignore the linter. `standard` still catches real bugs.

- **`requires-python = ">=3.12,<3.13"`** — an upper bound, unlike the hello-uv skeleton this is
  modelled on. Research dependencies in this space lag new Python releases, and an unpinned upper
  bound turns that into a resolution failure at an inconvenient moment.

- **Module headers are a `#` banner above a docstring** — the banner gives the visual break used
  throughout `dev-conv-agent`; the docstring is what `help()`, IDE hover and `?` in a notebook
  actually read. Comments are discarded by the parser, so a `#`-only header leaves `__doc__` as
  `None`. Because ASA is packaged and meant to be imported, that matters more here than in a
  notebook-driven project.

### Considered and rejected

- **GitHub's stock Python `.gitignore`** — replaced by a curated ~50-line file. Beyond being
  mostly irrelevant (Django, Celery, Scrapy, PyBuilder), it ignores **`lib/`**, which would
  silently drop a future `lib/` directory — `dev-conv-agent` has exactly such a directory. It
  also lacks the `.vscode/*` allowlist that keeps shared editor config tracked while ignoring
  personal noise. The coverage section was carried across as the one part worth keeping.

- **ruff `D` (pydocstyle)** — considered and not enabled. Docstrings are written everywhere by
  convention, but not machine-enforced. Noted for anyone revisiting it: the
  `[tool.ruff.lint.pydocstyle] convention` key is not optional, because without it ruff warns
  that D203/D211 and D212/D213 are mutually incompatible and chooses for you.

- **`from __future__ import annotations`** — dropped from the modules this scaffold is derived
  from. It exists so pre-3.10 interpreters can parse modern type hints; this project is pinned to
  3.12 only, so it is noise.

- **A hardcoded `__version__`** — read from the installed metadata instead
  (`importlib.metadata.version`), so `pyproject.toml` is the single source of truth rather than
  one of two copies that drift. [`CITATION.cff`](../CITATION.cff) still needs syncing by hand on
  a version bump.

- **`scripts/`** — the hello-uv skeleton carries an empty `scripts/` placeholder. Dropped: an
  empty directory that documents an intention nobody has acted on is clutter.
