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

  *Superseded 2026-07-28: `furhat-realtime-api>=0.1.3` added when [`session.py`](../src/asa/session.py)
  landed and needed to talk to a robot. The principle held rather than failed — it stayed empty
  through the whole scaffold and the first entry arrived only when real code required it.*

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

- **In-module section dividers are a rule between two `#` lines**, ruled to a uniform 90 columns:

  ```python
  #
  # ── Dates and IDs ───────────────────────────────────────────────────────────────────────
  #
  ```

  Adopted when [`core/affect.py`](../src/asa/core/affect.py) grew past the point where its type
  definitions read as a single list. Comments here rather than docstrings, and the reasoning is
  the *reverse* of the module-header decision above: a divider groups a file for someone reading
  it top to bottom, and there is no object for `help()` to attach it to. It is navigation, not
  API documentation. The uniform width is the part worth stating — three dividers of three
  different lengths read as an accident rather than a structure, and nothing in the toolchain
  enforces it. Ruff will not flag drift: `W` is not in `select`, so trailing whitespace and
  ragged rules are both invisible to `uv run pytest`.

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

---

## 2. Test strategy for a robot the tests cannot assume

The agent's one collaborator is a physical-ish device reached over a websocket. It is not always
running, it is slow, and exercising it makes it talk. That shapes every choice below.

- **A fake client by default** — [`test_session.py`](../tests/test_session.py) replaces
  `AsyncFurhatClient` with a recording double, so the suite needs no robot, no network and no
  ports. This is not a compromise: what can actually regress is the code *this project* wrote
  around the client — the protocol dict built by hand in `gesture()`, the mapping of two transport
  exceptions onto one domain error, the lifecycle guards — and a fake exercises all of it in
  milliseconds.

- **A recording double, not a stub** — the fake keeps what it was asked to do. Several session
  methods return `None`, so the only evidence of correct behaviour is the event that went out.
  `gesture()` sending `"monitor": True` is invisible to any assertion on a return value.

- **One live test, and it skips rather than fails** —
  [`test_furhat_integration.py`](../tests/test_furhat_integration.py) is the only thing that can
  catch *protocol drift*: a fake will accept `monitor: True` for ever, even if the Furhat stops
  honouring it. It is guarded by a 0.2s socket probe, because the SDK being closed is the normal
  state and a suite that goes red for that reason stops being read.

- **Patch where the name is looked up** — `asa.cli.ASASession` and `asa.session.AsyncFurhatClient`,
  not the modules that define them. `from X import Y` copies the reference into the importing
  module, so patching the original leaves the caller holding the real class. The failure mode is
  nasty: the test still passes, having quietly exercised the real code.

- **Sync tests driving coroutines through `asyncio.run()`** — no async plugin. `pytest-asyncio`
  would be a dependency and `anyio` (already present) needs a marker plus a backend fixture, both
  for syntax that saves one line per test.

### Considered and rejected

- **An integration test with no skip guard** — the honest-looking option, and unusable in
  practice. The launcher is shut far more often than it is open, so the suite would be red by
  default and the signal would be ignored within a week.

- **Testing "unreachable" by pointing at a dead address** rather than stubbing the session. It
  passes today only because nothing is listening. The day a Furhat *is* running locally the test
  silently inverts: it connects, drives the real robot mid-suite and still reports green.

- **A custom `integration` marker** — needs registering in `[tool.pytest.ini_options]` to avoid
  unknown-mark warnings, and then a flag to deselect. `skipif` needs no configuration and prints
  the reason, which is also the fix: *start the Furhat launcher*.

- **Asserting on log message text** — tempting, since the handlers log. Rejected: it would turn
  every wording change into a test failure and teach you to edit tests to match wording rather
  than to check behaviour.

- **Testing the contents of `interaction()`** — it is a placeholder meant to change every time
  something new is tried. Pinning it would make experimentation cost a test edit.

---

## 3. Configuration, and where shipped data lives

*Implements ASA Design v0.1 §11 and §14.1.*

Configuration for a research prototype is not the same problem as configuration for an
application. Its job is to make a recorded result attributable: which settings produced this data,
and can that be reconstructed months later. Every choice below follows from that.

- **Three layers, each winning over the one before** — packaged defaults
  ([`src/asa/core/defaults.toml`](../src/asa/core/defaults.toml)), then an override file passed as
  `--config`, then command-line arguments. The override need only carry the keys it changes, so a
  pilot's config file is a short statement of *what was different*, which is also what you want to
  quote in a write-up.

- **The command-line layer is applied in `main()` alone**, not inside `load_config()`. The loader
  therefore knows nothing about `sys.argv`, so a notebook can build a `Config` without inventing a
  fake command line — the same reasoning that keeps `asyncio.run()` in `main()` alone.

- **`--host` has no argparse default.** It defaults to `None`, meaning *not given*, and
  `main()` resolves `args.host or config.furhat_host`. A real default there would make the
  argument always present, and it would then silently beat every configuration file — a bug that
  presents as "`--config` doesn't work".

- **An unknown key or section raises.** Not a warning, not ignored. The silent version is the
  dangerous one for research: the run quietly uses the default while your notes record the value
  you meant to set, and nothing in the results says otherwise.

- **The defaults ship inside the package** and are read through `importlib.resources`, not
  `__file__` or a relative path, so they resolve from any working directory and from a real
  install as well as the editable one. Verified: `uv build` puts `asa/core/defaults.toml` in the
  wheel, so `uv_build` needs no package-data setting.

- **Configuration lives in `core/`.** The membership test for that package is *depended on by
  everything, depending on nothing* — configuration passes it, since any adapter may read config
  and config imports nothing from `asa`.

- **Shipped data files sit next to the module that reads them**, rather than being gathered into
  one configuration directory. `defaults.toml` holds *tunables* — what changes per run.
  A planned `llm/models.toml` will hold *reference data* — model IDs, pricing, context windows;
  facts that change when a provider changes its catalogue, not when you run a different trial.
  Filing them together would imply an interchangeability that does not exist.

### Considered and rejected

- **A config file at the repository root.** It is only findable when the process happens to run
  from the repo root, so it works from the terminal and fails from a notebook or an installed
  copy — losing the one property that packaging bought.

- **`pyproject.toml` as the home for settings.** It is build and tooling metadata. Retuning a
  mapping table for a pilot should not mean editing the file that carries the version and the
  linter configuration.

- **A top-level `asa/config.py`**, on the grounds that configuration is infrastructure rather than
  domain. Defensible, but it splits the *depends-on-nothing* group across two places for a
  distinction nothing else in the codebase acts on.

- **One `config/` directory holding every TOML.** Appealing — a single place to find every knob —
  but it separates data from the code that consumes it, and would stop `llm/` being
  self-contained, which matters because that layer is copied to and from `dev-conv-agent` rather
  than shared as a dependency.

- **Warning on unknown keys rather than raising.** A warning in a research run is a line in a log
  nobody reads until the results look strange.
