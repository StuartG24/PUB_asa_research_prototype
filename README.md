# asa-research-prototype

> Research prototype for a basic **Artificial Social Agent** — a [uv](https://docs.astral.sh/uv/)-managed, packaged Python project.

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

---

## About

As a first step in investigating empathic social robots, a research prototype (`asa-research-prototype`) will be used to examine and refine a proposed framework for social interaction and to explore candidate technology solutions and evaluation approaches. The technology basis for the prototype will be the incremental building of an Artificial Social Agent.

**The agent is at an early stage.** The package contains `ASASession`, which opens and owns a
connection to a (virtual) Furhat robot, alongside a test suite that proves the packaging, tooling
and environment all work end to end. See [Roadmap](docs/roadmap.md) for what is planned.

It is a **packaged** project — it has a `[build-system]`, so `uv sync` builds and installs it
into the local `.venv`. That is what makes `import asa` resolve everywhere (tests, notebooks,
the console script) with no `sys.path` manipulation.

### A note on the three names

They deliberately differ, and it helps to know which is which:

| Name | Where it appears |
| ---- | ---------------- |
| `asa_research_prototype` | the repository and directory |
| `asa-research-prototype` | the distribution — `pyproject.toml`, `CITATION.cff`, `uv pip show` |
| `asa` | the import — `from asa import ASASession` |

The short import name comes from `[tool.uv.build-backend] module-name` in
[`pyproject.toml`](pyproject.toml), which overrides uv's default of deriving the module
directory from the project name.

---

## Documentation

| Document | Covers |
| -------- | ------ |
| This README | What the project is, how to install it, how to run it |
| [Architecture](docs/architecture.md) | How the pieces fit together, plus a file-by-file walkthrough |
| [Design decisions](docs/decisions.md) | Why it is built this way — numbered, append-only |
| [Roadmap](docs/roadmap.md) | What is built, and the planned extensions |

---

## Project structure

```text
asa_research_prototype/
├── src/asa/            # The importable package
│   ├── session.py      # ASASession — one async interaction session with the Furhat
│   ├── cli.py          # main() — the `asa` console command
│   ├── __main__.py     # enables `python -m asa`
│   ├── core/           # shared foundations — configuration, and the agent's core types
│   └── _tools/         # private dev utilities (logging, dependency report, port check)
├── notebooks/          # Exploratory & prototype notebooks
├── tests/              # pytest suite
├── docs/               # Architecture notes, design decisions and roadmap
├── data_in/            # Input data — contents gitignored, kept via .gitkeep
├── data_results/       # Results data — contents gitignored, kept via .gitkeep
└── pyproject.toml      # Metadata, dependencies, tool config (ruff, autopep8, pytest)
```

---

## Prerequisites

- **Python 3.12** — provisioned automatically by uv (see `.python-version`); no manual install needed.
- **[uv](https://docs.astral.sh/uv/)** — the package & environment manager:

  ```bash
  # macOS / Linux
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # or with Homebrew
  brew install uv
  ```

---

## Getting started

```bash
# 1. Clone
git clone https://github.com/StuartG24/asa_research_prototype.git
cd asa_research_prototype

# 2. Create the environment, install dependencies, build and install the package
uv sync
```

uv reads `.python-version`, provisions Python 3.12 (downloading it if necessary), creates a
local `.venv/`, installs the locked dependencies, and installs this project itself in **editable**
mode — so edits to `src/asa/` take effect immediately, with no re-sync.

One `uv sync` is enough: the `dev` group includes the `notebook` group, so test, lint and
notebook tooling all arrive together. CI that wants none of it can use `--no-default-groups`.

You don't need to activate the venv — prefix commands with `uv run` and they execute inside the
project environment.

---

## Usage

```bash
uv run asa               # the `asa` console script
uv run python -m asa     # the module entry point (same behaviour)
```

Both open a session with the Furhat, play a gesture, speak a line and disconnect. **The Furhat
launcher must be running** — with nothing serving on port 9000 the command reports one line and
exits 1 rather than raising.

The two entry points prove different things, which is why both exist: the console script exercises
the whole packaging path (`[project.scripts]` → installed entry point), while `python -m asa`
bypasses that and tests only that the package imports and its `__main__` shim works. If packaging
broke, the first would fail and the second would still pass.

| Option | Effect |
| ------ | ------ |
| `--host ADDRESS` | Furhat address. Default comes from configuration — `127.0.0.1`, the virtual Furhat |
| `--config FILE` | TOML file overriding selected configuration keys (see [Configuration](#configuration)) |
| `--log {debug,info,warning}` | Log verbosity (default `debug`) |

**Work in notebooks:**

```bash
uv run jupyter lab
```

Notebooks in `notebooks/` execute from the repo root (set in `.vscode/settings.json`), so
relative paths like `data_in/…` resolve. `import asa` works from anywhere regardless, because
the package is installed.

---

## Development

**Lint** — ruff, configured in `pyproject.toml`:

```bash
uv run ruff check .          # lint
uv run ruff check --fix .    # lint and apply safe autofixes
```

**Format** — autopep8, *not* `ruff format`:

```bash
uv run autopep8 --diff --recursive src/ tests/       # preview
uv run autopep8 --in-place --recursive src/ tests/   # apply
```

The split is deliberate: ruff lints and sorts imports; autopep8 formats, because it enforces
PEP 8 while leaving hand-arranged function signatures alone, whereas `ruff format` re-stacks
parameters all-or-nothing. Note the different path arguments — ruff excludes `.venv/` and
gitignored paths by default, autopep8 does not, so it is scoped to `src/ tests/` rather than `.`.

In VS Code, autopep8 runs on save and ruff sorts imports on save
(see [`.vscode/settings.json`](.vscode/settings.json)). The recommended extensions are listed in
[`.vscode/extensions.json`](.vscode/extensions.json).

**Manage dependencies** (edits `pyproject.toml`, updates `uv.lock`, syncs `.venv` in one step):

```bash
uv add <package>                     # runtime dependency
uv add --group dev <package>         # dev-only tool
uv add --group notebook <package>    # notebook-only tool
uv remove <package>
```

> `uv.lock` and `.python-version` are committed for reproducibility — don't edit them by hand.
> After pulling changes, run `uv sync` to bring your environment up to date.

---

## Configuration

Two separate things, deliberately kept apart.

**Settings** — TOML, in three layers, each winning over the one before:

1. [`src/asa/core/defaults.toml`](src/asa/core/defaults.toml), shipped inside the package so it
   resolves by module location rather than working directory;
2. an override file — `uv run asa --config pilots/pilot-2.toml` — which need only carry the keys
   it changes;
3. command-line arguments, applied in `main()` alone.

An unknown key or section in an override file is an **error**, not a warning. A mistyped key would
otherwise leave the default silently in place while your notes record the value you meant to set —
the sort of thing that invalidates a run without anybody noticing.

**Secrets and environment-specific values** — a local `.env` file (gitignored):

```bash
cp .env.example .env
```

Nothing is required yet: no environment variables are read. See [`.env.example`](.env.example) for
the conventions to follow as the prototype grows.

---

## Testing

The suite uses [pytest](https://docs.pytest.org/), installed with the `dev` dependency group.
Run it from the repo root:

```bash
uv run pytest              # run everything
uv run pytest -vv -rA -l   # verbose: full summary, plus local variables on failure
```

| Test file | Covers |
| --------- | ------ |
| [`tests/test_cli.py`](tests/test_cli.py) | argument parsing, the configuration fallback and the CLI override, and that an unreachable Furhat exits 1 instead of raising |
| [`tests/test_config.py`](tests/test_config.py) | the two-layer configuration load — packaged defaults, partial overrides, and the rejection of unknown keys and sections |
| [`tests/test_session.py`](tests/test_session.py) | `ASASession` against a fake client — actions, lifecycle and error mapping, with no robot and no network |
| [`tests/test_furhat_integration.py`](tests/test_furhat_integration.py) | one live round trip — connect, gesture, speak, disconnect. **Skipped** unless a Furhat is serving on port 9000 |
| [`tests/test_lint.py`](tests/test_lint.py) | runs `ruff check` across the repo as a test, so `uv run pytest` is also the lint gate |

Everything except the integration test runs in milliseconds and needs nothing installed or
running. The integration test skips itself when nothing answers on port 9000, so the suite stays
green with the Furhat SDK closed — start the launcher to include it, and note that it makes the
robot speak. To see which tests were skipped and why:

```bash
uv run pytest -rs
```

Configuration lives in `pyproject.toml` under `[tool.pytest.ini_options]`. Note there is no
`pythonpath` setting: because the project is installed into `.venv`, `import asa` resolves
without putting the repo root on `sys.path`.

In VS Code, the **Testing** panel (the flask icon) discovers and runs the same tests.

---

## License

This project is licensed under the **Apache License 2.0** — see [LICENSE](LICENSE) for the full
text. Copyright © 2026 Stuart Gow.
