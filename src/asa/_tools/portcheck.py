#
# Kernel / Port Diagnostic Utility
#

"""Show which Jupyter kernels are running, what TCP ports they hold, and clear the litter.

Written after a stale kernel belonging to *another* project was assigned ZMQ ports
9000-9004 at launch, and so silently occupied 9000 — the port the virtual Furhat listens
on. The websocket handshake then failed with::

    websockets.exceptions.InvalidMessage: did not receive a valid HTTP response

which points nowhere near the real cause. A kernel picks its five ZMQ ports from the
ephemeral range when it starts, so *any* kernel can land on 9000. Nothing is misconfigured
when it happens, it is luck, and it will recur.

Three questions, answered separately because they have different answers:

- who is holding the port I want?   -> ``port_holder()``, which covers any process, kernel or not;
- what kernels are alive?           -> ``running_kernels()``;
- what junk is left behind?         -> ``stale_connection_files()`` / ``clean()``.

A kernel is identified by the ``--f=<connection file>`` argument on its own command line,
which is authoritative. Matching connection files to kernels by *port* looks tempting and
is wrong: Jupyter allots ports from a narrow range and never deletes the file when a kernel
dies, so hundreds of dead files carry ports that a later kernel now holds.

Pure standard library, so it adds nothing to the lock file. A private development utility
(see ``asa._tools``), not part of the public API::

    from asa._tools import portcheck

    portcheck.report()              # kernels, litter count, and whoever holds the Furhat port
    portcheck.clean()               # dry run: list what would be deleted
    portcheck.clean(dry_run=False)  # actually delete
"""

import json
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

# The virtual Furhat's websocket endpoint is ws://<host>:9000/v1/events.
FURHAT_PORT = 9000

# Jupyter writes one connection file per kernel here and does not remove it when the kernel
# dies, so this directory accumulates thousands of dead files over a project's life.
RUNTIME_DIR = Path.home() / "Library" / "Jupyter" / "runtime"

# The kernel's own command line names its connection file: "... --f=/path/to/kernel-abc.json".
_CONNECTION_FILE_RE = re.compile(r"--f=(\S+\.json)")

# ".../<project>/.venv/bin/python" — the directory holding the venv names the project far
# more usefully than the interpreter path does.
_VENV_RE = re.compile(r"([^/]+)/\.venv/bin/python")


@dataclass(frozen=True)
class Listener:
    """A process holding a TCP port open for listening."""

    port: int
    pid: int
    command: str  # short name as lsof reports it, e.g. "python3.12"


@dataclass(frozen=True)
class Kernel:
    """A live Jupyter kernel, tied back to the project whose venv it runs from."""

    pid: int
    project: str  # best-effort project name, "?" if the command line does not reveal one
    ports: tuple[int, ...]  # the ZMQ ports from its connection file, ascending
    age: str  # elapsed run time, as ps reports it (e.g. "29:25")
    connection_file: Path
    is_current: bool  # True when this is the very kernel executing this code


def listening_ports() -> dict[int, Listener]:
    """Map every listening TCP port on this machine to the process holding it.

    Uses lsof's field output (``-F``) rather than its human table: the columns are
    space-aligned and a command name containing a space would break naive splitting.
    """
    try:
        completed = subprocess.run(
            ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pcn"],
            capture_output=True, text=True, timeout=10.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}

    holders: dict[int, Listener] = {}
    pid, command = 0, "?"
    for line in completed.stdout.splitlines():
        if not line:
            continue
        tag, value = line[0], line[1:]
        if tag == "p":
            pid, command = int(value), "?"
        elif tag == "c":
            command = value
        elif tag == "n":
            # Address looks like "127.0.0.1:9000", "*:8888" or "[::1]:9000".
            _, _, port_text = value.rpartition(":")
            if port_text.isdigit():
                holders[int(port_text)] = Listener(int(port_text), pid, command)
    return holders


def port_holder(port: int = FURHAT_PORT) -> Listener | None:
    """Return the process listening on ``port``, or None if the port is free."""
    return listening_ports().get(port)


def _process_field(pid: int, spec: str) -> str:
    """Read one ps field for ``pid``, or "" if the process has gone."""
    try:
        completed = subprocess.run(["ps", "-p", str(pid), "-o", spec],
                                   capture_output=True, text=True, timeout=5.0)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip()


def _ipykernel_processes() -> list[tuple[int, str, Path]]:
    """Return (pid, command line, connection file) for every live ipykernel process.

    ``-ww`` disables ps's column truncation. Without it a long interpreter path can cut the
    ``--f=`` argument off the end, and the connection file — the thing that makes this
    identification authoritative — would be silently lost.
    """
    try:
        completed = subprocess.run(["ps", "-ww", "-Ao", "pid=,command="],
                                   capture_output=True, text=True, timeout=10.0)
    except (OSError, subprocess.TimeoutExpired):
        return []

    processes: list[tuple[int, str, Path]] = []
    for line in completed.stdout.splitlines():
        if "ipykernel_launcher" not in line:
            continue
        pid_text, _, command = line.strip().partition(" ")
        match = _CONNECTION_FILE_RE.search(command)
        if pid_text.isdigit() and match:
            processes.append((int(pid_text), command, Path(match.group(1))))
    return processes


def running_kernels() -> list[Kernel]:
    """Return every Jupyter kernel that is actually alive, ascending by PID."""
    kernels: list[Kernel] = []
    for pid, command, connection_file in sorted(_ipykernel_processes()):
        try:
            config = json.loads(connection_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}

        match = _VENV_RE.search(command)
        kernels.append(Kernel(
            pid=pid,
            project=match.group(1) if match else "?",
            ports=tuple(sorted(value for key, value in config.items()
                               if key.endswith("_port") and isinstance(value, int))),
            age=_process_field(pid, "etime=") or "?",
            connection_file=connection_file,
            is_current=pid == os.getpid(),
        ))
    return kernels


def stale_connection_files(min_age_minutes: float = 5.0) -> list[Path]:
    """Return the kernel connection files that belong to no live kernel.

    Files younger than ``min_age_minutes`` are spared regardless: a kernel that is still
    starting up has written its file but may not be visible in ps yet, and deleting that
    file would strand it.

    Only ``kernel-*.json`` is considered. The ``jpserver-*`` files in the same directory
    belong to the Jupyter *servers*, not kernels, and removing a live one hides the running
    server from ``jupyter server list``.
    """
    live = {k.connection_file.resolve() for k in running_kernels()}
    cutoff = time.time() - min_age_minutes * 60

    stale: list[Path] = []
    for path in sorted(RUNTIME_DIR.glob("kernel-*.json")):
        if path.resolve() in live:
            continue
        try:
            if path.stat().st_mtime > cutoff:  # too new to judge — a kernel may be launching
                continue
        except OSError:
            continue
        stale.append(path)
    return stale


def clean(dry_run: bool = True, min_age_minutes: float = 5.0) -> list[Path]:
    """Delete the stale connection files. Returns the files deleted (or, on a dry run, listed).

    Defaults to a dry run — pass ``dry_run=False`` to actually unlink. Deleting these costs
    nothing: a connection file is scratch state for a kernel that has already exited, and
    nothing of yours is stored in it.
    """
    stale = stale_connection_files(min_age_minutes=min_age_minutes)

    if dry_run:
        print(f"Dry run: {len(stale)} stale connection files in {RUNTIME_DIR}")
        print("Pass dry_run=False to delete them.")
        return stale

    deleted: list[Path] = []
    for path in stale:
        try:
            path.unlink()
            deleted.append(path)
        except OSError:  # already gone, or not ours to remove
            continue

    print(f"Deleted {len(deleted)} stale connection files from {RUNTIME_DIR}")
    return deleted


def report(port: int = FURHAT_PORT) -> list[Kernel]:
    """Print the kernel table and the verdict on ``port``, and return the kernel rows."""
    kernels = running_kernels()

    headers = ("PID", "PROJECT", "AGE", "PORTS", "NOTE")
    cells = [(str(k.pid), k.project, k.age, ", ".join(str(p) for p in k.ports),
              "<- this kernel" if k.is_current else (f"HOLDS PORT {port}" if port in k.ports else ""))
             for k in kernels]

    if cells:
        widths = [max(len(h), *(len(row[i]) for row in cells)) for i, h in enumerate(headers)]

        def line(values: tuple[str, ...]) -> str:
            return "  ".join(v.ljust(w) for v, w in zip(values, widths, strict=True)).rstrip()

        print(line(headers))
        print(line(tuple("-" * w for w in widths)))
        for row in cells:
            print(line(row))
    else:
        print("No running Jupyter kernels.")

    stale = stale_connection_files()
    if stale:
        print(f"\n{len(stale)} stale connection files in {RUNTIME_DIR} — clean() to remove them.")

    # The port verdict is deliberately separate: the blocker is often not a kernel at all.
    holder = port_holder(port)
    print()
    if holder is None:
        print(f"Port {port}: free — nothing is listening, so start the Furhat launcher before connecting.")
    else:
        culprit = next((k for k in kernels if k.pid == holder.pid), None)
        if culprit is None:
            print(f"Port {port}: held by {holder.command} (pid {holder.pid}).")
        else:
            print(f"Port {port}: held by the '{culprit.project}' kernel (pid {holder.pid}) — "
                  f"a ZMQ port collision, not the Furhat.")
            print(f"           Free it with:  from asa._tools import portcheck; portcheck.shutdown({holder.pid})")

    return kernels


def shutdown(pid: int) -> bool:
    """Ask kernel ``pid`` to exit (SIGTERM). Returns True if the signal was delivered.

    Refuses to signal the current process, so running this from a notebook can never kill
    the kernel you are typing into. In-memory state in the target kernel is lost — files on
    disk are not touched.
    """
    if pid == os.getpid():
        raise ValueError(f"PID {pid} is the current kernel — refusing to shut it down")
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return False
    return True
