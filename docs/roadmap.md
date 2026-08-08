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
- [x] **Tests** — pytest suite covering the CLI and the session (against a fake client), a
      skip-guarded live Furhat round trip, and ruff lint as a test ([`tests/`](../tests))
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

**Done — the agent, as far as the fold**

Built against a design document held outside this repository (an Obsidian vault note, *ASA Design*),
whose version is stamped into every run through `design_version` in
[`defaults.toml`](../src/asa/core/defaults.toml). Each item below has a numbered entry in
[Design decisions](decisions.md).

- [x] **The core record types** — `AffectVector`, `Utterance`, `AffectEvidence`, `AffectState`,
      `AffectHistory`, plus the expression records
      ([`core/affect.py`](../src/asa/core/affect.py),
      [`core/expression.py`](../src/asa/core/expression.py)) · decision 4
- [x] **Affect representations as declared data** — `basic4/1` and `ekman6/1` declare their axes,
      range, rest point and whether distance between vectors is meaningful
      ([`core/representations.py`](../src/asa/core/representations.py)) · decision 8
- [x] **A publish-only observer registry** — components announce; listeners record and cannot answer
      back ([`core/observers.py`](../src/asa/core/observers.py)) · decision 5
- [x] **Type checking in the suite** — `pyright` over `src` and `tests` as an ordinary test
      ([`tests/test_types.py`](../tests/test_types.py)) · decision 6
- [x] **One evidence queue and one consumer**, with a teardown order that cannot be rearranged
      ([`core/loops.py`](../src/asa/core/loops.py)) · decision 7
- [x] **Perception** — two ports, a console adapter that reads without freezing the event loop, a
      keyword decoder with one lexicon per representation, and a driver
      ([`perception/`](../src/asa/perception)) · decision 9
- [x] **The four-layer rule** — `core/`, then ports and strategies plus one `drive.py`, then
      `runtime.py`, then `cli.py` as composition root
      ([`runtime.py`](../src/asa/runtime.py)) · decision 10
- [x] **Benchmark data preparation** — labelled corpora reshaped into one standard frame carrying
      provenance, with unannotated axes left unmeasured rather than filled
      ([`notebooks/`](../notebooks))

`uv run asa` therefore hears a line, publishes it, decodes it to an affect estimate, queues that, and
**stops at the affect model**, which raises rather than inventing a belief. An empty session exits 0.

**Planned — next**

- [ ] **The affect model** — the research core, and the first component the design cannot fully
      specify in advance. Folds evidence into belief per target, ages it lazily so that time is a
      parameter rather than a clock read, and answers `state_at(t)`. Lands as `belief.py`,
      `folding.py` and `decay.py`, replacing the stub that currently raises
- [ ] **The intention planner** — the first proactive component, deciding on its own clock how the
      agent should feel and publishing that as evidence about itself
- [ ] **Encoding and embodiment** — affect to a platform-neutral expression plan, then to a robot;
      the first end-to-end run happens here, with no robot involved
- [ ] **`session.py` becomes `embodiment/furhat.py`** — a refactor of shipped, tested code, at which
      point `--furhat-demo` is deleted
- [ ] **Recording** — append-only JSONL streams plus a run manifest. The manifest must carry content
      hashes and every model parameter, not just a commit, or a recorded belief cannot be reproduced
- [ ] **The evaluation channel** — recognition and RoSAS prompts, written as a stream that links back
      to the render it asks about

**Planned — near-term housekeeping**

- [ ] **Complete `CITATION.cff`** — add `orcid:`, and a `doi:` if the work is ever archived
      (e.g. Zenodo)

---
