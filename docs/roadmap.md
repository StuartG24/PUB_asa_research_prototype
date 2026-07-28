# Roadmap

What is built and what is planned. [Architecture](architecture.md) describes how the shipped
pieces work; [Design decisions](decisions.md) records why they are built that way.

Relative links below are written from the repository root.

---

**Done — the scaffold**

- [x] **Packaged uv project** — `[build-system]` with `uv_build` and a `src/` layout; `uv sync`
      builds and installs it editable, so `import asa` resolves everywhere
      ([`pyproject.toml`](../pyproject.toml))
- [x] **Short import name** — `[tool.uv.build-backend] module-name = "asa"`, keeping the
      distribution name `asa-research-prototype`
- [x] **Package entry points** — a CLI entry point (`asa`) and a `-m` shim
      ([`src/asa/`](../src/asa))
- [x] **Tests** — pytest suite covering the CLI, and ruff lint as a test
      ([`tests/`](../tests))
- [x] **Tooling** — ruff as linter and import-sorter, autopep8 as formatter, both configured in
      `pyproject.toml` and wired into VS Code ([`.vscode/`](../.vscode))
- [x] **Repository hygiene** — curated `.gitignore`, `.env.example`, data directories kept via
      `.gitkeep`
- [x] **Documentation** — [README](../README.md), [Architecture](architecture.md),
      [Design decisions](decisions.md), this roadmap, and [`CITATION.cff`](../CITATION.cff)

- [x] **Replaced the placeholder** — `Greeter` and its test deleted now that
      [`session.py`](../src/asa/session.py) has landed; `main()` is a genuine composition root
      rather than a packaging smoke test
- [x] **First runtime dependencies** — `furhat-realtime-api` added, exercising the
      resolve → lock → install path for real

**Planned — near-term**

- [ ] **Furhat connection** — `ASASession` connects, speaks and gestures; next is perception
      (`request_listen_start` and the `response_hear` event) so a turn can be driven by what the
      user says rather than a fixed script
- [ ] **Complete `CITATION.cff`** — add `orcid:`, and a `doi:` if the work is ever archived
      (e.g. Zenodo)

**Planned — the agent**

> Not yet specified. The research direction determines what goes here, and recording guesses as
> if they were decisions would be worse than leaving the section honest. Fill this in as the
> prototype's scope firms up, and add the corresponding numbered entries to
> [Design decisions](decisions.md) as each choice is actually made.

---
