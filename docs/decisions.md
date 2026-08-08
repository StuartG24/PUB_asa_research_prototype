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

---

## 4. The agent's core types — records, not objects with behaviour

*Implements ASA Design v0.3 §4, §5 and §5.4.*

[`core/affect.py`](../src/asa/core/affect.py) and [`core/expression.py`](../src/asa/core/expression.py)
hold frozen dataclasses and nothing else. They are the vocabulary every other component speaks, and
they were built first because a record shape is the hardest thing in this project to change later: it
is written into research data, and a pilot's files outlive the code that produced them.

- **A vector names its representation as a plain `str`, and nothing validates the link.** An
  `AffectVector` carrying `representation="basic4/1"` and an axis that representation does not
  declare is built without complaint. That is deliberate. Records outlive code, so a stream from an
  earlier pilot may name a representation this build no longer declares, and validating on
  construction would make that data unopenable by the current code. Validation happens at the seams
  instead: the producer builds a correct vector, the interpreter asserts the representation it
  supports and fails loudly on anything else.

- **Evidence and state are different types, so the fold rule is enforced rather than remembered.**
  `AffectEvidence` is an *estimate at an instant*; `AffectState` is the model's *belief*. Keeping
  them apart means an estimate cannot be assigned over a belief anywhere in the codebase — the type
  checker refuses it. `AffectObservation` is an alias for `AffectEvidence`, not a new type:
  perception produces evidence like anything else and is distinguished by `source`.

- **Timezone-naive datetimes are rejected, not coerced.** `_require_aware` raises, because a naive
  datetime does not say *which clock* it came from and guessing would silently shift every timestamp
  in a recording. Contrast the tuple coercion below, which is a coercion precisely because it has one
  right answer.

- **`AffectHistory` coerces its sequences to `tuple` in `__post_init__`** rather than merely
  annotating them. Verified empirically: without the coercion, `states=[s1, s2]` is accepted, stays a
  mutable list, and `.append()` on it succeeds — a type annotation guarantees nothing at runtime. The
  reasoning ports are promised a snapshot, an LLM call may sit behind one, and a live handle would
  give torn reads.

- **The snapshot is not *deeply* immutable, and the affect model has to honour that.** Each
  `AffectState` is frozen, but the `values` mapping inside its vectors is an ordinary `dict`, and
  `frozen=True` protects the binding rather than the contents. So the outer guarantee holds only if
  folding builds **new** `AffectVector` objects instead of mutating one in place. Cheap to honour
  from the model's first line; expensive once anything reads history asynchronously.

- **`schema` is a per-record shape tag**, one of four independent versioning axes in this project
  alongside `space`/`representation`, `design_version` and the package `__version__`. A record says
  what shape it is, so an analysis reading two pilots' files can tell them apart without guessing
  from the field names present.

- **Enum members are `StrEnum`, and that is load-bearing rather than cosmetic.** Verified: a
  `StrEnum` member hashes as its *value*, so `{Emotion.HAPPINESS: 0.9}["happiness"]` resolves — the
  MRO puts `str.__hash__` ahead of `Enum.__hash__`. A plain `Enum` hashes by member *name* and would
  raise `KeyError`. That is what makes `Mapping[str, float]` a safe declaration for a mapping the
  code populates with enum keys, and it holds for pandas index lookups too.

- **Two field names collide with pandas accessors and were kept anyway.** `df.at` is the scalar
  indexer and `df.values` the numpy array, so attribute access on a DataFrame silently returns the
  wrong object while `df["at"]` and `df["values"]` work. Both names are right in the domain; this is
  a notebook gotcha to know rather than a reason to rename a record field that will appear in data.

- **Tested for guards and for properties other components depend on, not for fields.** These types
  are nearly pure data, so asserting that a field round-trips would test `dataclasses` rather than
  this module. Deliberately not tested: value ranges (nothing enforces them by design), that
  `frozen=True` blocks assignment, and that a defaulted `at` is "about now" — a clock race for no
  information.

- **`asdict()` leaves datetimes as `datetime` objects**, so `json.dumps` on a whole record fails.
  Pinned by a test, because the consequence lands on the recorder: it needs a `default=` handler for
  datetimes and for nothing else, since enum members serialise unaided.

- **A third vector records what the agent *conveyed*, held apart from what it feels.**
  `AffectState.expressed` and `Target.EXPRESSED` took the tag to `state/2`. Merged into `self_`,
  *intended* and *conveyed* would become one number and "did the agent express what it meant?"
  would stop being answerable — which is much of what a study of empathic expression is asking.
  It is a fact rather than an estimate, so it is assigned rather than weighted and never decays;
  and nothing lets it reach `self_`, so this is not facial feedback.

- **`EXPRESSED` is deliberately not named for a channel.** Iteration 1 expresses through the face
  alone, but what is recorded is *affect*, in the representation's axes, not the machinery that
  produced it — so the same member covers tone of voice, gesture and posture as they arrive.
  Naming it `FACIAL` would have needed renaming the day a second channel is driven
  independently, and renaming a `Target` costs a `schema` bump and two record shapes in one
  analysis. Which channel did what is recorded on the render instead, where `ExpressionPlan`
  already distinguishes a face channel from a voice channel.

  **The known limit:** one vector cannot say that the face conveyed one thing and the voice
  another, and a channel disabled by an experimental condition is *not applicable* rather than
  at rest. Both arrive when two channels are driven independently, and both are left open rather
  than guessed at.

### Considered and rejected

- **`MappingProxyType` for `AffectVector.values`**, to make the mapping read-only. `asdict()` raises
  `TypeError: cannot pickle 'mappingproxy'`, which breaks serialisation — the one thing these types
  exist to survive.

- **Making `AffectVector` generic in its axis type**, so a checker could reject an unknown axis where
  the literal is written. The parameter propagates through evidence, state, history and every port
  signature; it is the same value everywhere, since a run uses one representation throughout; and it
  is erased at the JSON boundary, so the records an analysis reads gain nothing.

- **Renaming `rationale` to `deliberation_rationale`.** Asked and rejected: `source` already names
  the producer, so a producer-specific name would be a second source of truth that can contradict
  it. Vindicated later — the intention planner and the keyword decoder both fill `rationale` now, so
  the qualified name would already be a lie. The field name is also the JSONL key, so renaming after
  pilot data means a `schema` bump and two record shapes in one analysis.

- **A `context` field reserved for the framework's Context/Background moderators.** An always-`None`
  field with no type is documentation that lies, and it is trivial to add the day a `Context` type
  exists.

---

## 5. Observation without participation — a publish-only registry

*Implements ASA Design v0.3 §3.2.*

[`core/observers.py`](../src/asa/core/observers.py) is 117 lines of which 69 are docstring — the
mechanism is small and the reasoning is not. It exists so that recording never becomes a participant
in the behaviour being recorded: components announce what happened, and whoever is listening writes it
down and cannot answer back.

- **One shared registry, not one per component.** The design's wording reads both ways, and one
  object passed to all four components means an observer registers *once*. The alternative has the
  composition root registering the recorder four times, and once more for every component added
  later.

- **`publish()` is synchronous.** A JSONL append is tens of microseconds against a 100 ms render
  tick, and streams are required to buffer nothing, which rules out the background writer `async`
  would buy. A side benefit decided the timing: it made this module's tests plain synchronous tests,
  so it did not have to wait for the async test strategy the evidence loop still needed.

- **A broken observer is logged and dropped, and cannot reach control flow.** `except Exception`, not
  `BaseException`, so a faulty recorder cannot swallow `KeyboardInterrupt` mid-session.

- **The failure handler must not read the event.** The first sketch logged
  `"failed on %s", event.schema` — evaluated *inside* the `except` block, so an event without a
  `schema` raises `AttributeError` out of `publish()`, breaking the exact guarantee the class exists
  to make. Verified both ways. The fix is also simpler: pass the event itself and let `logging` defer
  formatting.

- **`Event` is a `Protocol` with read-only properties, and Pylance caught a real bug there.**
  Declared as bare attributes (`at: datetime`), a protocol demands *writable* attributes, which every
  record type fails because they are all frozen — so the protocol did not describe the very types it
  was written for. Read-only properties are satisfied by frozen records, and a mutable attribute
  satisfies a read-only requirement too, so asking for less excludes nothing.

- **The runtime check and the static check genuinely disagree here.** An earlier demonstration used
  `@runtime_checkable` plus `isinstance` and returned `True`, because `isinstance` on a protocol
  checks only that attributes *exist* — never whether they are writable. A protocol claim is a static
  claim and must be checked with a type checker.

- **`Observer` is a `Callable[[Event], None]` alias, and the `None` return is the contract.** A
  callable that cannot return a value cannot influence what published it. Note the alias is
  *contravariant* in its parameter: an observer must accept any `Event`, so a helper annotated for a
  narrower type is correctly rejected.

### Considered and rejected

- **`@runtime_checkable` on `Event`.** It would imply the registry validates its input, when it
  checks only that attributes exist rather than their types.

- **An ABC instead of a Protocol.** Being structural, `observers.py` imports none of the record types
  and none of them import it. With an ABC, `core/affect.py` would have had to depend on the capture
  mechanism — the wrong direction for a module every layer is allowed to use.

- **Wrapping the queue to capture events from one place.** The events worth recording originate in
  four components and no one of them sees the others, so a wrapper would capture a fraction and imply
  it had captured everything.

---

## 6. Type checking as part of the test suite

*Implements ASA Design v0.3 §15 (the `Types` row).*

[`tests/test_types.py`](../tests/test_types.py) runs `pyright` over `src` **and** `tests` as an
ordinary test. Ruff lints but does not type-check, so before this the entire class of typing error was
editor-only and invisible to `uv run pytest` — which is how twelve accumulated in one sitting.

- **`pyright`, not `mypy`**, because it is the engine Pylance wraps. The gate then agrees with the
  editor. A different checker would disagree with the editor in both directions and teach you to
  distrust one of them.

- **`pyright[nodejs]` as a dev dependency, not `uvx`.** Pyright is a Node program; the plain package
  pulls `nodeenv` and downloads Node at first run, so a fresh clone could not run the suite offline.
  The `[nodejs]` extra ships Node as a wheel, so `uv sync` installs it and `uv.lock` pins it.

- **It checks `tests` as well as `src`, and that is load-bearing.** The `Event` protocol bug was in
  `src` but produced no error there — `observers.py` violates nothing on its own, and the mismatch
  only appears at a call site. Ten of the twelve errors found on the first run were in test files.

- **Configuration lives in `[tool.pyright]` in `pyproject.toml`.** Verified that pyright loads it, and
  Pylance reads the same section — so `python.analysis.typeCheckingMode` was removed from
  `.vscode/settings.json` and replaced by a comment pointing at `pyproject.toml`. One source of
  truth; the editor and the suite cannot drift.

- **A new file, not an addition to `test_lint.py`.** A file called `test_lint` holding a type check is
  the same naming lie this project keeps rejecting elsewhere.

- **Cost measured, and teeth verified.** The rest of the suite runs in about 0.3 s; this one test adds
  about 1.3 s, which is most of the total wall time and is worth it. A deliberately planted type error
  fails with the exact file, line and pyright message in the pytest output.

- **The `# type: ignore` comments are deliberate and each is narrow.** Nine of them, all in tests,
  every one marking a line that is *intentionally* type-invalid because the runtime behaviour is the
  subject: `attr-defined` where a test proves a tuple has no `.append`, `arg-type` where a list is
  passed to prove it gets coerced, `call-arg` and `index` likewise. The error code is always named, so
  a blanket `# type: ignore` cannot hide a second, unintended problem on the same line.

### Considered and rejected

- **Leaving type checking to the editor.** It is the status quo that allowed twelve errors to
  accumulate unseen, and it makes correctness depend on which editor a collaborator opens.

- **`typeCheckingMode = "strict"`.** It flags "unknown type" throughout from under-typed
  dependencies, which trains you to skim the output. `"standard"` catches real bugs and is read.

- **Running pyright only in CI.** There is no CI on this project yet, and a check that runs somewhere
  the author does not look is a check that is discovered to be failing later.

---

## 7. One queue, one consumer, and a teardown whose order is not interchangeable

*Implements ASA Design v0.3 §3, §3.4 and §9.2.*

[`core/loops.py`](../src/asa/core/loops.py) holds the evidence queue and the single consumer task that
drains it. Producers submit; one loop folds and publishes. The shape exists so that the affect model
has exactly one writer, and so that a session can end without losing what a participant generated.

- **The queue and the loop are two different things**, and conflating them is the natural mistake.
  The queue is an `asyncio.Queue` — a buffer that takes no decision and knows nothing. The loop is
  the consumer task that drains it, hands each item to the model, publishes what happened and stops
  cleanly.

- **`EvidenceLoop` owns its queue rather than being handed one**, so producers hold a bound `submit`
  method and never see the transport. Least privilege, too: the object would also expose `drain()`,
  which a producer must never call, since draining waits for producers to have stopped.

- **Only the loop publishes evidence, whichever producer made it.** Perception, deliberation and the
  intention planner all submit and none of them publishes. Three producers each remembering to
  publish is three chances to forget, and the fourth somebody adds later silently loses data.

- **The evidence row is written *before* the fold, and the ordering carries information.** If the
  model then raises, the evidence that caused it is already in the record rather than only in a
  traceback — and the failure acquires a signature that costs no extra field: **an evidence row with
  no state row after it is a fold that did not complete.**

- **A failing fold ends the session rather than being absorbed.** The model has no network and no
  language model in it, so it has nothing to fail intermittently *with*; a raise from it is a bug,
  not a transient. That is why there are no retry counts and no failure thresholds.

- **The failed item is still acknowledged**, so a fatal fold cannot become a hang instead of an
  error.

- **`StateWriter` is a `Callable` alias rather than a Protocol**, because the affect model is
  deliberately not a port — it owns state and a lifetime instead of being a transform, so there is no
  interface to name. `core/` also may not import `affect_model/`, so a named port would have to be
  flattened here anyway.

- **`observe` must stay synchronous, and this is a constraint on the affect model.** The loop has no
  `await` between taking an item and marking it done *only* because publishing is synchronous and
  the state writer is a plain callable. An `async` fold would silently destroy that atomicity and
  reopen the shutdown hang.

- **Teardown order: stop the producers, drain what they left, then cancel the consumer.** Cancelling
  first would discard evidence the participant generated and that `utterances.jsonl` says happened —
  a recording that looks complete and is not.

- **Both ways of getting the teardown wrong hang, for different reasons, and one of them falsified a
  docstring.** Cancelling before draining does not lose the tail as first written: `drain()` is
  `queue.join()`, which waits for one `task_done()` per item *taken*, and a cancelled consumer takes
  no more — so the wait never ends. Omitting the cancel hangs too, because a task group waits for a
  `while True` child. Same symptom, two causes.

- **Wrap a timeout where the characteristic failure is a hang, and nowhere else.** The runtime tests
  use `asyncio.wait_for`, unlike the perception tests. It earned itself immediately: three tests
  failed *by name* in 6.4 s instead of hanging the suite.

### Considered and rejected

- **Two queues, one for evidence and one for actions.** The action queue went with the affect model's
  emission: lazily-evaluated state cannot push, so there was nothing to put on it.

- **A message bus or a broker process.** Recorded as the shape this would grow into if a second
  process ever needed the stream, and rejected for iteration 1 because the queue is one object behind
  a `submit` method — swapping it is a change in one place rather than one per producer.

- **A synchronous pipeline of function calls.** Cannot express autonomy: it must poll for speech
  events, and it has nowhere to put decay or deliberation.

- **Retry counts and failure thresholds on the fold.** They answer a question this design already
  answered by putting everything slow, non-deterministic and failure-prone on the far side of the
  queue.

---

## 8. Affect representations as declared data

*Implements ASA Design v0.4 §5.1, §5.3 and §8.4.*

[`core/representations.py`](../src/asa/core/representations.py) declares what an affect vector's axis
names *mean*: which axes exist, in what order, over what range, what they rest at, and whether distance
between two of them is meaningful. Before this, claims like "values are 0.0–1.0" and "decay heads for
zero" were stated in prose as though they were truths about affect. They are properties of one *kind*
of representation, and the module exists so that a component reads them instead of assuming them.

- **`rest` is a declared field, and it is the consequential one.** A model that decayed every
  representation toward zero would be correct for an intensity scale, where zero is the *absence* of
  an emotion — and wrong for a dimensional one, where zero is a *position*: on a 0–1 valence scale,
  zero is maximally negative, so decaying toward it would age a neutral person into misery. The affect
  model reads `rest` rather than assuming it, which is what keeps the model representation-agnostic.

- **`metric` is declared because the analysis has to branch on it.** A categorical representation is a
  set of categories held in a vector for uniformity; the midpoint between anger and surprise is not an
  emotion. So an aggregate error across its axes — a mean, and still more a Euclidean distance —
  asserts a commensurability it does not have. A future `vad/1` may legitimately use distance. The
  flag is what lets one piece of analysis code serve both without guessing.

- **No field has a default, deliberately.** A defaulted `metric=False` would let a dimensional
  representation silently declare itself non-metric, which is the error with no symptom: every figure
  computed from it would be quietly wrong rather than absent.

- **Four declaration guards, all raising.** No axes, a duplicate axis, an inverted `value_range`, and a
  `rest` outside that range. A representation is a claim about meaning; a malformed one should not
  reach the data.

- **`axes` is coerced to `tuple`, not merely annotated as one** — the same reasoning as
  `AffectHistory`, and for the same demonstrated reason: an annotation guarantees nothing at runtime,
  and a list would let a caller mutate a declared basis after the fact.

- **Class names describe the axis count, not a theorist.** `FourEmotions` and `SixEmotions`, because a
  name crediting a theorist would make a later variation an argument about attribution rather than
  about axes.

- **`basic4/1`'s axes are merges, not a subset** — `fear_surprise` and `anger_disgust` share an axis
  each. So the two declared representations differ in **resolution rather than coverage**, which makes
  them a good test of the plug-in seam and a poor test of the hard cross-representation case, where
  categorical meets dimensional and no agreed mapping exists.

- **The registry is keyed by the id that appears in data.** `REPRESENTATIONS["ekman6/1"]` is how an
  analysis resolves a string it read from a JSONL row months later, which is the only lookup that has
  to work.

- **The axis vocabularies are pinned *whole* in the tests**, as the facial vocabulary is:
  `{axis.value for axis in SixEmotions} == {…}`. An axis added or removed silently changes the shape of
  every record written in that representation, and both failures are invisible at the point someone
  would make them.

### Considered and rejected

- **A `rest` value per axis rather than one per representation.** Sufficient for every representation
  declared, and a dimensional one may well want per-axis rest — arousal at rest and valence at rest
  are not the same claim. Deferred to the representation that needs it, rather than carried as a field
  nothing varies.

- **Declaring whether axes are *bipolar*.** Plutchik's wheel pairs opposites; these do not. Left
  undeclared because no component would read it yet, and a field nothing reads is documentation that
  can rot.

- **Deriving `basic4/1` from `ekman6/1`.** Merging two axes needs a rule — maximum, sum, mean — and
  each is defensible and they disagree on real data. Making it a derivation would bake an unrecorded
  research choice into every comparison.

---

## 9. Perception — two ports, and a decoder that is stateless on purpose

*Implements ASA Design v0.4 §8.1, §8.2, §8.3 and §8.4.*

[`perception/base.py`](../src/asa/perception/base.py) declares two protocols and
[`text_console.py`](../src/asa/perception/text_console.py) and
[`decode_keyword.py`](../src/asa/perception/decode_keyword.py) implement one each. The split follows the
framework: producing an utterance and interpreting one are two elements, and much of the research
consists of varying the second while holding the first fixed.

- **`InputSource.events()` returns an `AsyncIterator`, and that type is the whole design.** The next
  utterance does not have to be *computed*, it has to be *waited for* — a person decides when to
  speak. An ordinary iterator could only block the single thread while that happens, freezing the
  render loop and the intention planner with it.

- **`events` is declared as a plain `def` returning an `AsyncIterator`**, not as an `async def`. That
  is satisfied both by an async generator function (what the adapters are) and by a plain function
  handing back somebody else's iterator. Both are callables returning an async iterator, which is all
  the port asks for.

- **The console reader is `asyncio.to_thread(self._read, self._prompt)`, with the argument passed
  separately.** `to_thread` takes the function *and* its arguments; writing
  `to_thread(self._read(self._prompt))` calls the reader first, on the event loop, which is the freeze
  the thread exists to prevent — and then passes the resulting string to be called, which fails. A
  test asserts the loop keeps running during a read by advancing a counter task concurrently: without
  the thread it cannot advance at all. That is the one decision here that could be "simplified" away
  with every other test still passing.

- **The reader is an injected callable, never a patched `builtins.input`.** A test that monkey-patches
  ends up testing the patch, and the injection is also what let a notebook supply its own
  end-of-input sentinel, since no notebook frontend can send a real EOF.

- **The decoder is `async` for its successor, not for its incumbent.** A keyword lookup could not be
  more synchronous, but Decode & Infer becomes an LLM inference, and a port whose implementations
  disagree about async-ness cannot be swapped — every caller would change with the implementation,
  which is the one thing a port exists to prevent.

- **The decoder is stateless, and that is load-bearing rather than tidy.** It sees the utterance and
  nothing else: no history, no access to the belief it is contributing to. That is what makes the
  planned rule-versus-LLM comparison valid, since both see identical input and neither is confounded
  by accumulated state. Interpretation that depends on prior state is a real research direction and is
  deferred as an explicit claim rather than smuggled in.

- **Every axis of the representation is present, at rest where nothing fired.** A representation names
  a basis, so a vector in it carries every axis of that basis. Two things follow: every row in
  `evidence.jsonl` has the same axes in the same order, so the analysis has no missing values to
  decide about; and the affect model is spared an ambiguity between "no claim, leave it alone" and
  "claimed nothing", which are opposite behaviours that would otherwise be settled by accident.

- **A sentence with no emotion word decodes to the rest vector, not to nothing.** Under a vector
  representation that *is* "no affect expressed", exactly — which is why there is no NEUTRAL axis. What
  the model does with such an observation is the fold's decision: the decoder reports, the model
  believes.

- **Several matches combine per axis by `max`, not by summing.** "Delighted but astonished" is an
  ordinary human state and these are independent intensities rather than a distribution, so both axes
  rise. Summing within an axis would leave the declared range and would make a word repeated for
  emphasis read as a stronger feeling.

- **The axes are walked in the representation's order, not the table's.** The table is a literal
  somebody wrote and its order is a convention; the representation's order is the one the record is
  written in.

- **`rationale` carries the words that fired as `axis=word` pairs, including a word that lost the
  `max`.** It is there for the benchmark: measuring how well decoding works means asking not only
  whether a sentence scored correctly but *why* it did not, and the vector alone cannot say — "good
  grief" scoring as mild happiness looks identical to a sentence that really was mildly happy. A word
  that fired and was overruled is exactly what an error analysis needs.

- **`confidence` is left `None`.** A keyword matched or it did not, and a fabricated `1.0` would make
  this decoder look maximally certain beside an LLM honestly reporting 0.7. `None` means *unstated*,
  which is a different fact from *certain*.

- **One table per representation, written independently rather than derived.** `EKMAN6_KEYWORDS` is not
  generated from `BASIC4_KEYWORDS`: the six-way split is a different judgement about which words signal
  which emotion, not a mechanical expansion. The standing cost is that word coverage has to be kept
  level between them by hand, and it is noted in the module rather than left to be discovered when one
  representation scores better for having more words.

- **Accuracy is deliberately not tested here.** The suite tests guards and shape — the port is
  satisfied, `source` and the representation are stamped, several matches combine, a sentence with no
  emotion word yields the rest vector. A suite that fails when a table scores 62% is reporting a
  finding as a defect, and it will be muted.

### Considered and rejected

- **One port for perception and decoding together.** They are separate framework elements — text,
  speech and generated input are three ways of hearing; rule and LLM decoding are two ways of
  interpreting — and merging them would make swapping either mean reimplementing both.

- **Letting the adapters publish their own events.** Both are pure producers. Three adapters each
  remembering to publish is three chances to forget, and the fourth somebody adds later silently loses
  data.

- **Spreading `confidence` across axes to express uncertainty.** A decoder torn between two readings
  says so in the vector, `{happiness: 0.5, surprise: 0.5}`, rather than picking one and attaching a
  confidence of 0.5. They are different quantities and conflating them makes both unreadable.

---

## 10. Four layers — ports, drivers, runtime, composition root

*Implements ASA Design v0.5 §14, §14.1 and §14.2.*

Where a thing lives is decided by one question: what may it import, and who may import it.

| Layer | Rule | Holds |
| --- | --- | --- |
| [`core/`](../src/asa/core) | depends on nothing; everything may depend on it | types, config, observers, the evidence loop |
| subpackages | ports and strategies, plus one driver module named `drive.py` | `perception/{base,text_console,decode_keyword,drive}.py` |
| [`runtime.py`](../src/asa/runtime.py) | may import anything; imported only by `cli.py` and notebooks | `run_agent()` — every long-lived task, in one place |
| [`cli.py`](../src/asa/cli.py) | the composition root — the only place naming a concrete adapter | args, logging, config, one `asyncio.run()` |

- **A package names a region of the framework; a module names a strategy.** So `perception/` is the
  producer side of the cycle and `text_console.py`, `furhat_speech.py`, `decode_keyword.py` are ways of
  being one. Never repeat the package name inside a module name — `affect_model/model.py` and
  `intention/intention_mimicry.py` both stutter at the import site.

- **A package may hold one driver module, named `drive.py`, and it is the only non-strategy module
  allowed there.** A driver turns ports into a running task: `perception/drive.py` holds the `async for`
  that hears an utterance, publishes it, decodes it and submits the result. It names no strategy, so
  the rule above does not cover it.

- **`runtime.py` exists so that "what is running?" has one answer**, and it *calls* drivers rather than
  containing them. Nothing in it constructs an adapter, which is what lets a notebook — already owning
  an event loop — drive a whole agent with fakes by awaiting `run_agent` directly.

- **A driver may not live in `__init__.py`, and this is the objection that settled the layer.** The run
  must be visible to someone tracing control flow, and `__init__.py` is the least visible name
  available. The same objection was later sustained against the rule that produced it, moving the
  affect model out of its own package's `__init__.py`.

- **The driver takes a bound `submit` method, not the evidence loop.** Least privilege: the object would
  also hand over `drain()`, which a producer must never call. A side benefit is that a driver test needs
  no evidence loop at all, so a broken loop cannot fail a driver test.

- **Publish the utterance *before* decoding it, and two tests pin that from opposite sides.** Removing
  the `try/except` fails one test; swapping publish and submit fails two — and the second failure is the
  informative one, because publishing after the decode means a failed decode leaves **no trace of the
  utterance at all**. The ordering is what makes the failure readable, not merely ordered.

- **The evidence loop is constructed in `runtime.py`; the observer registry in `cli.py`.** The
  composition root chooses what can *vary*. Which observers watch a run is exactly a per-run choice; the
  evidence loop has no alternatives, so requiring every caller to build one correctly would be ceremony
  rather than composition.

- **Cancelling a child task from inside a `TaskGroup` body lets no `CancelledError` escape the group**,
  so no suppression is needed — demonstrated rather than assumed, because the opposite is widely
  assumed. A consequence worth having: because a dying consumer cancels the body wherever it stands,
  the rule "never drain after a fatal fold" becomes structurally unreachable rather than something
  anyone has to remember.

- **A fake input source must yield to the event loop between utterances.** An async generator with no
  `await` submits its whole script before the consumer runs once, and the published order then becomes
  an artefact of the fake — so an interleaving assertion would have been written around a fiction. The
  real console adapter yields naturally via `to_thread`.

- **`cli.py` names the only concrete adapters, and the Furhat demo path has a deletion date.**
  `--furhat-demo` exists until the session refactor lands, at which point it goes. A test patches
  `run_agent` and supplies a session class whose `__init__` raises, because asserting that a robot was
  *not* contacted needs something that objects.

### Considered and rejected

- **`run_perception()` in `perception/__init__.py`.** Rejected on the visibility grounds above, and the
  objection reshaped the whole layering.

- **The driver in `cli.py`.** The composition root is scoped to wiring, and a driver there cannot be
  tested without standing up the CLI.

- **A single top-level `asa/actors.py`.** The design lists four actors and then adds "plus producer
  tasks — the input adapters", so perception is *not* an actor and the name would misdescribe the first
  thing put in it.

- **`Callable` seams in `core/loops.py` instead of named ports.** `core/` may not import `perception/`,
  so both named ports would flatten into `Callable` aliases at exactly the place a reader wants their
  names — and unlike `StateWriter`, nothing forces it.
