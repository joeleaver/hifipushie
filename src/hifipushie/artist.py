"""hifipushie as an oxidegen artist: the `sculpt` artist of the Art Department, run as a LOCAL RUNNER.

    uv run hifipushie-artist                 (token in $OXIDEGEN_RUNNER_TOKEN or ~/.config/hifipushie/runner-token)

The runner dials out to the department (oxidegen's artist/1 contract, docs/artist-contract.md §10) and pulls work:
register -> heartbeat (a thread) -> long-poll `next` -> run the task -> post its result. Nothing listens.

- Capabilities are derived from the live tool registry (`mcp.list_tools()`), so new tools show up by themselves,
  through a small policy table (`POLICY`): `name` is the session's subject, host paths are dropped (inputs arrive as
  library versions, outputs leave as task files), tools that make no sense for a department are left out.
- A session (`_open` ... `_close`) gets its own workspace (work_root/<session id>, HIFIPUSHIE_HOME for the tools)
  and its own worker subprocess (artist_worker.py) in its own process group: a cancel kills the whole group,
  Blender included, and the next task starts a fresh worker. The live-Blender socket is off (HIFIPUSHIE_NO_LIVE).
- Standalone hifipushie (the MCP server) is untouched: this is only an extra entry point.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import logging
import os
import platform
import queue
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("hifipushie.artist")

CONTRACT = "artist/1"
ARTIST = "sculpt"
DEFAULT_URL = "https://oxidegen.jkbase.app"
SAFE_NAME = re.compile(r"[A-Za-z0-9_\-]+")
PROGRESS_SECS = 10.0
EXIT_UNAUTHORIZED = 77  # the department refused the token: don't retry (systemd: RestartPreventExitStatus)
DISCONNECTED = "This computer was disconnected; run hifipushie-artist setup to connect again."

# ---------------------------------------------------------------------------------------------- capabilities

FAST = {"guide", "kit_reference", "get_model", "put_model", "edit_model", "history", "revert", "measure",
        "clearance", "set_reference", "set_plan", "check",
        "look"}  # ~10 s at the default resolution: worth waiting for inline (a big close-up becomes a task to poll)
SLOW = {  # (documentation: anything not fast or very_slow is slow, new tools included)
    "compare", "fit", "rig", "style_check", "sync", "set_terrain", "check_terrain", "export", "snapshot"}
VERY_SLOW = {"export_asset", "look_terrain", "export_terrain"}
MUTATES = {"put_model", "edit_model", "revert", "set_plan", "fit", "set_reference", "set_terrain", "sync",
           "terrain_history"}  # terrain_history: only with revert_to, but it can
BLENDER = {"look", "rig", "style_check", "sync", "export_asset", "look_terrain", "export_terrain", "snapshot"}
NO_BLENDER = FAST | {"compare", "fit", "set_terrain", "check_terrain", "export", "terrain_history"}
IMAGES = {"look", "set_reference", "compare", "fit", "set_plan", "check", "rig", "export_asset", "look_terrain",
          "snapshot"}
FILES = {"export", "export_asset", "export_terrain", "snapshot"}
PAINTED = {"look", "style_check"}  # render the Blender scene in EEVEE by default (painted looks; style colours)

# Left out of the department: they list or reach the host (every model on this machine; the person's Blender).
EXCLUDE = {"list_models": "lists every model on this machine, not the session's subject",
           "pull": "takes edits back from a person's Blender on this machine (a standalone feature)"}
# Tools that take no subject are only offered when known to be harmless (an unknown one might list the host).
SUBJECTLESS_OK = {"guide", "kit_reference"}

# Host-path parameters: dropped from the schema. Their values are set by the runner (outputs into the task's
# scratch dir) or not at all. Unknown tools: any string parameter with a path-like name is dropped too.
HOST_PATH_NAMES = {"save", "path", "out_dir", "out", "dir", "file", "filepath", "image_path"}

IMAGE_INPUT = {"type": "string", "x-oxidegen": "version", "description": "a library version id (an image)"}


@dataclass
class Policy:
    drop: tuple = ()                     # parameters removed (the runner fills the required ones)
    fill: dict = field(default_factory=dict)  # parameter -> how the runner fills it: "obj", "dir"
    inputs: dict = field(default_factory=dict)  # new parameter -> (tool parameter it becomes, schema)
    restrict: dict = field(default_factory=dict)  # parameter -> regex its string value must match


POLICY = {
    "look": Policy(drop=("save",), restrict={"matcap": r"[A-Za-z0-9_.\-]+"}),  # a "/" loads any host file
    "set_plan": Policy(drop=("save",)),
    "check": Policy(drop=("save",)),
    "rig": Policy(drop=("save",)),
    "style_check": Policy(drop=("save",)),
    "set_reference": Policy(drop=("image_path",), inputs={"image": ("image_path", IMAGE_INPUT)}),
    "export": Policy(drop=("path",), fill={"path": "obj"}),
    "export_asset": Policy(drop=("out_dir", "save"), fill={"out_dir": "dir"}),
    "export_terrain": Policy(drop=("out_dir",), fill={"out_dir": "dir"}),
}


def subject_kinds(tool: str, takes_name: bool) -> list[str]:
    if not takes_name:
        return ["model", "terrain"]
    return ["terrain"] if "terrain" in tool else ["model"]


def _is_string(schema: dict) -> bool:
    if schema.get("type") == "string":
        return True
    return any(s.get("type") == "string" for s in schema.get("anyOf", []) if isinstance(s, dict))


def _host_path_param(pname: str, schema: dict) -> bool:
    return _is_string(schema) and (pname in HOST_PATH_NAMES or pname.endswith(("_path", "_dir", "_file")))


def _title(desc: str) -> str:
    """The description's first sentence (or clause), as a short title."""
    first = re.split(r"(?<=[a-z)])[.:;] ", " ".join(desc.split()), maxsplit=1)[0].rstrip(".")
    return first if len(first) <= 80 else first[:77].rsplit(" ", 1)[0] + "..."


def capability(tool) -> tuple[dict | None, str]:
    """One tool of the registry as an artist/1 Capability (None and why, when it's left out)."""
    name = tool.name
    if name in EXCLUDE:
        return None, EXCLUDE[name]
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", name):
        return None, "not a valid capability name"
    schema = copy.deepcopy(tool.input_schema or {"type": "object", "properties": {}})
    props = schema.setdefault("properties", {})
    required = list(schema.get("required") or [])
    takes_name = "name" in props
    if not takes_name and name not in SUBJECTLESS_OK:
        return None, "takes no subject and isn't known to be harmless"
    pol = POLICY.get(name, Policy())
    drop = set(pol.drop) | {p for p, s in props.items() if p != "name" and _host_path_param(p, s)}
    for p in sorted(drop):
        if p in required and p not in pol.fill and p not in {v[0] for v in pol.inputs.values()}:
            return None, f"needs a host path ({p}) the runner doesn't know how to fill"
    for p in drop | {"name"}:
        props.pop(p, None)
    required = [r for r in required if r not in drop and r != "name"]
    for new, (_, sch) in pol.inputs.items():
        props[new] = dict(sch)
        required.append(new)
    for p, rx in pol.restrict.items():
        if p in props:
            props[p]["pattern"] = f"^{rx}$"
    schema["required"] = required
    if not required:
        schema.pop("required")
    schema.pop("title", None)
    desc = tool.description or ""
    timing = "fast" if name in FAST else "very_slow" if name in VERY_SLOW else "slow"
    returns = ["text"] + (["image"] if name in IMAGES else []) + (["file"] if name in FILES else [])
    return {
        "tool": name,
        "title": tool.title or _title(desc) or name,
        "description": desc,
        "input_schema": schema,
        "returns": returns,
        "publishes": False,
        "timing": timing,
        "mutates_subject": name in MUTATES,
        # painted looks render in EEVEE, which wants a GPU-capable context: on a local runner Blender finds one;
        # the department-facing flag stays false (a hosted sculpt-cpu box would need the split, contract §7)
        "needs": {"gpu": False, "blender": name in BLENDER or name not in NO_BLENDER},
        "subject_kinds": subject_kinds(name, takes_name),
    }, ""


SNAPSHOT = {
    "tool": "snapshot",
    "title": "Snapshot the subject",
    "description": ("The subject's current spec as a file (role \"spec\", spec.json) plus a quick look (a clay contact "
                    "sheet for a model, the map for a terrain), so a spec-only working state can be published. "
                    "look=false skips the image."),
    "input_schema": {"type": "object", "properties": {
        "look": {"type": "boolean", "default": True, "description": "include a quick look image"}}},
    "returns": ["text", "image", "file"],
    "publishes": False,
    "timing": "slow",
    "mutates_subject": False,
    "needs": {"gpu": False, "blender": True},
    "subject_kinds": ["model", "terrain"],
}


def capabilities(preload: list[str] = ()) -> tuple[list[dict], dict]:
    """(capabilities, {left-out tool: why}) from the live registry, plus the adapter's own `snapshot`."""
    import importlib
    for mod in preload:
        importlib.import_module(mod)
    from .server import mcp
    caps, left = [], {}
    for t in asyncio.run(mcp.list_tools()):
        cap, why = capability(t)
        if cap:
            caps.append(cap)
        else:
            left[t.name] = why
    caps.append(copy.deepcopy(SNAPSHOT))
    return caps, left


def instructions() -> str:
    from .server import INSTRUCTIONS
    return (INSTRUCTIONS + "\nAs the department's sculpt artist: a session works on ONE subject (a model or a terrain), so "
            "tools take no `name`. Files never come as host paths: set_reference takes `image`, a library version id; "
            "exports come back as task files (glb, fbx, obj, maps, json, and the spec). `snapshot` returns the spec "
            "and a quick look, to publish a working state.")


# ---------------------------------------------------------------------------------------------- config

@dataclass
class Config:
    url: str = DEFAULT_URL
    token: str = ""
    name: str = ""
    work_root: Path = Path("~/.cache/hifipushie-artist").expanduser()
    assets: str | None = None
    mode: str = "local"
    preload: list = field(default_factory=list)
    probe: bool = False  # run the GPU/EEVEE readiness probe before registering (hosted boxes)
    updater: object = None  # artist_update.Updater (a local install that follows the department's pinned sha)
    update_failed: str | None = None  # a sha that couldn't be switched to (hosted start), reported in heartbeats


def hosted_config(env=None) -> Config:
    """A hosted box's config: env only (no token file, no flags needed). Raises ValueError naming what's missing."""
    env = os.environ if env is None else env
    missing = [k for k in ("OXIDEGEN_URL", "OXIDEGEN_RUNNER_TOKEN") if not env.get(k, "").strip()]
    if missing:
        raise ValueError(f"hosted mode needs {' and '.join(missing)} in the environment")
    return Config(url=env["OXIDEGEN_URL"].strip(), token=env["OXIDEGEN_RUNNER_TOKEN"].strip(),
                  name=env.get("OXIDEGEN_RUNNER_NAME", "").strip() or f"hosted-{socket.gethostname()}",
                  work_root=Path(env.get("HIFIPUSHIE_ARTIST_WORK") or "/work").expanduser(),
                  assets=env.get("HIFIPUSHIE_ASSETS") or None, mode="hosted", probe=True)


def _token(arg: str | None, token_file: str | None) -> str:
    if arg:
        return arg.strip()
    if os.environ.get("OXIDEGEN_RUNNER_TOKEN"):
        return os.environ["OXIDEGEN_RUNNER_TOKEN"].strip()
    p = Path(token_file).expanduser() if token_file else token_path()
    if p.exists():
        return p.read_text().strip()
    return ""


def _assets_default() -> str | None:
    """Where the third-party packs (GNM, MakeHuman) are: the runner's HIFIPUSHIE_ASSETS, else the person's usual
    HIFIPUSHIE_HOME/_templates (a session's HIFIPUSHIE_HOME is its own workspace, so it can't be found from there)."""
    if os.environ.get("HIFIPUSHIE_ASSETS"):
        return os.environ["HIFIPUSHIE_ASSETS"]
    for home in (os.environ.get("HIFIPUSHIE_HOME"), str(Path.cwd() / "workspace")):
        if home and (Path(home) / "_templates").is_dir():
            return str(Path(home) / "_templates")
    return None


# ---------------------------------------------------------------------------------------------- department API

class HTTPError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status
        self.body = body


class Unauthorized(Exception):
    """The department refused the runner's token (401/403): retrying won't help."""


class Department:
    def __init__(self, url: str, token: str):
        self.base = url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body=None, raw: bytes | None = None, ctype: str | None = None,
                timeout: float = 30.0):
        url = path if path.startswith(("http://", "https://")) else self.base + path
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method)
        if self.token:  # (pairing and the install manifest are public)
            req.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            req.add_header("Content-Type", ctype or "application/json")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                payload = r.read()
                status = r.status
        except urllib.error.HTTPError as e:
            raise HTTPError(e.code, e.read().decode(errors="replace")) from None
        if status == 204 or not payload:
            return None
        return json.loads(payload)

    def get_bytes(self, path: str, timeout: float = 300.0) -> bytes:
        url = path if path.startswith(("http://", "https://")) else self.base + path
        req = urllib.request.Request(url)
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            raise HTTPError(e.code, e.read().decode(errors="replace")) from None


# ---------------------------------------------------------------------------------------------- worker

class Canceled(Exception):
    pass


class WorkerDied(Exception):
    pass


class Worker:
    """A session's tool process, in its own process group (cancel = kill the group, Blender children included)."""

    def __init__(self, workspace: Path, assets: str | None, preload: list[str]):
        self.ws = workspace
        logf = workspace / "_artist" / "worker.log"
        logf.parent.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith("OXIDEGEN_")}  # the token stays here
        env.update(HIFIPUSHIE_HOME=str(workspace), HIFIPUSHIE_NO_LIVE="1")
        env.pop("BLENDER_MCP_PORT", None)
        if assets:
            env["HIFIPUSHIE_ASSETS"] = assets
        if preload:
            env["HIFIPUSHIE_ARTIST_PRELOAD"] = ",".join(preload)
        rfd, wfd = os.pipe()
        self._log = open(logf, "ab")
        self.proc = subprocess.Popen([sys.executable, "-m", "hifipushie.artist_worker", str(wfd)], cwd=workspace,
                                     env=env, stdin=subprocess.PIPE, stdout=self._log, stderr=self._log,
                                     pass_fds=(wfd,), start_new_session=True)
        os.close(wfd)
        self.pgid = self.proc.pid  # start_new_session: the worker leads its own group
        self.replies: queue.Queue = queue.Queue()
        self._rf = os.fdopen(rfd, "r")
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self._rf:
            try:
                self.replies.put(json.loads(line))
            except ValueError:
                continue
        self.replies.put(None)  # the worker is gone

    def alive(self) -> bool:
        return self.proc.poll() is None

    def ask(self, req: dict, tick=None, tick_secs: float = PROGRESS_SECS) -> dict:
        """Send a request and wait for its reply. tick() runs every tick_secs while waiting and every 0.25 s checks
        for a cancel: it returns True to cancel (then the group is killed and Canceled raised)."""
        self.proc.stdin.write((json.dumps(req) + "\n").encode())
        self.proc.stdin.flush()
        last = time.monotonic()
        while True:
            try:
                rep = self.replies.get(timeout=0.25)
            except queue.Empty:
                rep = ...
            if rep is None:
                self.kill()
                raise WorkerDied(f"the worker exited ({self.proc.returncode}); log: {self._tail()}")
            if rep is not ...:
                return rep
            due = time.monotonic() - last >= tick_secs
            if tick and tick(due):
                self.kill()
                raise Canceled()
            if due:
                last = time.monotonic()

    def _tail(self) -> str:
        try:
            return (self.ws / "_artist" / "worker.log").read_text(errors="replace")[-600:]
        except OSError:
            return ""

    def kill(self):
        try:
            os.killpg(self.pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        try:
            self._log.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------------------------- the runner

@dataclass
class Session:
    id: str
    kind: str
    name: str
    ws: Path
    worker: Worker | None = None


class Runner:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.dept = Department(cfg.url, cfg.token)
        self.caps, self.left_out = capabilities(cfg.preload)
        self.gpu = gpu_probe() if cfg.probe else None
        if self.gpu is not None:
            log.info("GPU probe: eevee %s, workbench %s (%s)", self.gpu["eevee"], self.gpu["workbench"],
                     self.gpu.get("renderer") or "no renderer")
            if self.gpu["eevee"] != "ok":
                for c in self.caps:
                    if c["tool"] in PAINTED:
                        c["needs"]["gpu"] = True
        self.cap_of = {c["tool"]: c for c in self.caps}
        self.exit_code = 0
        self.updater = cfg.updater
        self.wanted = None  # (sha, repo) the department wants this runner to run
        self.runner_id: str | None = None
        self.heartbeat_secs = 15.0
        self.poll_secs = 25.0
        self.progress_secs = PROGRESS_SECS
        self.session: Session | None = None
        self.task_id: str | None = None
        self.task_msg: str | None = None
        self.cancels: set[str] = set()
        self.lock = threading.Lock()
        self.need_register = threading.Event()
        self.uploaded: set[str] = set()
        self.stop = threading.Event()

    # -- registration and heartbeat

    def register(self):
        eq = equipment(self.cfg.work_root)
        if self.gpu is not None:
            eq.update(eevee=self.gpu["eevee"], workbench=self.gpu["workbench"], gpu_renderer=self.gpu.get("renderer"),
                      gpu_backend=self.gpu.get("backend"))
        body = {"name": self.cfg.name, "artist": ARTIST, "artist_version": artist_version(), "contract": CONTRACT,
                "mode": self.cfg.mode, "equipment": eq, "capabilities": self.caps,
                "instructions": instructions() + gpu_note(self.gpu)}
        if self._update_failed():
            body["update_failed"] = self._update_failed()
        try:
            r = self.dept.request("POST", "/v1/runners/register", body)
        except HTTPError as e:
            if e.status in (401, 403):
                raise Unauthorized(f"the department refused this runner's token (HTTP {e.status}: {e.body[:200]})")
            raise
        self.runner_id = r["runner_id"]
        self._wanted(r)
        if self.updater:
            self.updater.confirm()
        self.heartbeat_secs = float(r.get("heartbeat_secs") or 15)
        self.poll_secs = float(r.get("poll_secs") or 25)
        self.need_register.clear()
        self.uploaded.clear()
        if self.session:  # re-registering ends the department's side of it ("runner_restarted")
            log.info("re-registered: dropping session %s", self.session.id)
            self._drop_session()
        write_status({"state": "registered", "runner_id": self.runner_id, "name": self.cfg.name,
                      "url": self.cfg.url, "at": time.time(), "version": artist_version(), "pid": os.getpid()})
        log.info("registered %s as runner %s (%d capabilities; left out: %s)", self.cfg.name, self.runner_id,
                 len(self.caps), ", ".join(f"{k} ({v})" for k, v in self.left_out.items()) or "none")

    def _heartbeat_loop(self):
        last = 0.0
        while not self.stop.wait(0.2):  # (heartbeat_secs is only known after registering)
            rid = self.runner_id
            if not rid or self.need_register.is_set() or time.monotonic() - last < self.heartbeat_secs:
                continue
            last = time.monotonic()
            with self.lock:
                body = {"task": self.task_id, "message": self.task_msg}
            if self._update_failed():
                body["update_failed"] = self._update_failed()
            try:
                r = self.dept.request("POST", f"/v1/runners/{rid}/heartbeat", body) or {}
            except HTTPError as e:
                if e.status in (401, 403, 404):  # (re-registering tells a revoked token from a forgotten runner)
                    self.need_register.set()
                log.warning("heartbeat: %s", e)
                continue
            except OSError as e:
                log.warning("heartbeat: %s", e)
                continue
            with self.lock:
                self.cancels |= set(r.get("cancel") or [])
            self._wanted(r)

    def _wanted(self, reply):
        from .artist_update import wanted
        w = wanted(reply)
        if w:
            self.wanted = w

    def _update_failed(self) -> str | None:
        return (self.updater.last_failed() if self.updater else None) or self.cfg.update_failed

    def _maybe_update(self):
        """Idle (no session, no task): follow the department's pinned sha, or roll back a switch that never
        registered. On a switch this process becomes the new version (exec)."""
        u = self.updater
        if u is None or self.session is not None or self.task_id is not None:
            return
        if u.overdue(self.runner_id is not None):
            log.error("this version (%s) didn't register within a minute of the update: rolling back", u.current[:12])
            u.rollback("didn't register after the switch")
            self.shutdown()
            u.reexec()
        if u.due(self.wanted) and u.update(self.wanted) is None:
            self.shutdown()
            u.reexec()

    # -- main loop

    def run(self):
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        backoff = 1.0
        while not self.stop.is_set():
            try:
                if self.runner_id is None or self.need_register.is_set():
                    self.register()
                task = self.dept.request("POST", f"/v1/runners/{self.runner_id}/next", {},
                                         timeout=self.poll_secs + 15)
                backoff = 1.0
            except Unauthorized as e:
                log.error("%s: stopping", e)
                write_status({"state": "unauthorized", "name": self.cfg.name, "url": self.cfg.url,
                              "at": time.time(), "error": str(e)})
                self.exit_code = EXIT_UNAUTHORIZED
                break
            except HTTPError as e:
                if e.status in (401, 403, 404):
                    log.warning("department forgot this runner (%s): registering again", e.status)
                    self.need_register.set()
                else:
                    log.warning("next: %s", e)
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue
            except OSError as e:
                log.warning("department unreachable: %s", e)
                self._maybe_update()
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if task:
                self.handle(task)
            else:
                self._maybe_update()
        self.shutdown()

    def shutdown(self):
        self.stop.set()
        if self.session:
            self._drop_session()

    # -- tasks

    def handle(self, task: dict):
        tid = task["task_id"]
        with self.lock:
            self.task_id, self.task_msg = tid, f"{task.get('tool')} for session {task.get('session_id')}"
        t0 = time.monotonic()
        try:
            res = self._dispatch(task)
        except Canceled:
            res = {"status": "canceled", "content": [], "error": None}
        except WorkerDied as e:
            res = _error(str(e), retryable=True)
        except HTTPError as e:
            res = _error(f"department: {e}", retryable=True)
        except Exception as e:  # (the runner reports, it doesn't fall over)
            log.exception("task %s", tid)
            res = _error(f"{type(e).__name__}: {e}")
        if task.get("tool") == "_open" and res.get("status") != "ok" and self.session \
                and self.session.id == task.get("session_id"):
            self._drop_session()  # an open that failed (e.g. hydrating) leaves nothing behind
        res.setdefault("content", [])
        res.setdefault("files", [])
        res.setdefault("error", None)
        res.setdefault("questions", None)
        res["metering"] = {"wall_secs": round(time.monotonic() - t0, 3)}
        try:
            self.dept.request("POST", f"/v1/tasks/{tid}/result", res)
        except HTTPError as e:
            log.warning("result of %s: %s", tid, e)
        except OSError as e:
            log.warning("result of %s: %s", tid, e)
        with self.lock:
            self.task_id = self.task_msg = None
            self.cancels.discard(tid)

    def _dispatch(self, task: dict) -> dict:
        tool = task["tool"]
        if tool == "_open":
            return self._open(task)
        s = self.session
        if s is None or s.id != task["session_id"]:
            return _error(f"session {task['session_id']} isn't open on this runner")
        if tool == "_close":  # the workspace goes before the result says so
            self._drop_session()
            return {"status": "ok", "content": [{"type": "text", "text": "closed"}]}
        cap = self.cap_of.get(tool)
        if cap is None:
            return _error(f"no tool {tool!r} on this artist")
        if s.kind not in cap["subject_kinds"]:
            return _error(f"{tool} works on a {' or '.join(cap['subject_kinds'])}; this session's subject "
                          f"{s.name!r} is a {s.kind}")
        args = dict(task.get("args") or {})
        bad = sorted(set(args) - set(cap["input_schema"].get("properties", {})))
        if bad:
            return _error(f"{tool}: unknown argument(s) {bad}")
        if tool == "snapshot":
            return self._snapshot(task, bool(args.get("look", True)))
        pol = POLICY.get(tool, Policy())
        for p, rx in pol.restrict.items():
            if p in args and not (isinstance(args[p], str) and re.fullmatch(rx, args[p])):
                return _error(f"{tool}: {p} {args[p]!r} isn't allowed here (a name, not a path)")
        out = s.ws / "_artist" / "out" / _safe(task["task_id"])
        shutil.rmtree(out, ignore_errors=True)
        out.mkdir(parents=True)
        for new, (param, _) in pol.inputs.items():  # library versions -> files in the session's scratch dir
            args.pop(new, None)
            args[param] = str(self._fetch_input(task, new))
        files_dir = out / "files"
        for param, how in pol.fill.items():
            files_dir.mkdir(exist_ok=True)
            args[param] = str(files_dir / f"{s.name}.obj") if how == "obj" else str(files_dir)
        if tool not in SUBJECTLESS_OK:  # every other offered tool takes the subject's name (capability())
            args["name"] = s.name
        rep = self._call(task, {"op": "call", "tool": tool, "args": args, "out": str(out / "content")})
        if not rep.get("ok"):
            return _error(rep.get("error") or "the tool failed")
        content, questions = self._content(rep["content"])
        files = []
        if pol.fill:
            files = self._files(files_dir)
            files.append(self._spec_file())
        res = {"status": "ok", "content": content, "files": files}
        if questions is not None:
            res.update(status="needs_input", questions=questions)
        return res

    def _call(self, task: dict, req: dict) -> dict:
        s = self.session
        if s.worker is None or not s.worker.alive():
            s.worker = Worker(s.ws, self.cfg.assets, self.cfg.preload)
        tid = task["task_id"]

        def tick(due: bool) -> bool:
            with self.lock:
                if tid in self.cancels:
                    return True
            if not due:
                return False
            msg = self._progress_line()
            with self.lock:
                self.task_msg = msg or self.task_msg
            try:
                r = self.dept.request("POST", f"/v1/tasks/{tid}/progress",
                                      {"fraction": None, "message": msg or f"{req.get('tool', req['op'])} running"})
                return bool((r or {}).get("cancel"))
            except (HTTPError, OSError) as e:
                log.warning("progress: %s", e)
                return False

        try:
            return s.worker.ask(req, tick, self.progress_secs)
        except (Canceled, WorkerDied):
            s.worker = None  # restarted lazily for the next task
            raise

    def _progress_line(self) -> str | None:
        s = self.session
        base = s.ws / "terrain" / s.name if s.kind == "terrain" else s.ws / s.name
        p = base / "progress.log"
        try:
            lines = p.read_text(errors="replace").strip().splitlines()
        except OSError:
            return None
        return lines[-1][:500] if lines else None

    # -- session framing

    def _open(self, task: dict) -> dict:
        args = task.get("args") or {}
        subj = args.get("subject") or {}
        kind, name = subj.get("kind"), subj.get("name")
        if kind not in ("model", "terrain"):
            return _error(f"subject kind {kind!r}: this artist works on a model or a terrain")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name.startswith("_"):
            return _error(f"subject name {name!r}: letters, digits, _ and - only")
        wsname = str(args.get("workspace") or task["session_id"])
        if not SAFE_NAME.fullmatch(wsname):
            return _error(f"workspace {wsname!r} isn't a safe directory name")
        if self.session:
            log.warning("_open while session %s is open: dropping it", self.session.id)
            self._drop_session()
        ws = self.cfg.work_root / wsname
        shutil.rmtree(ws, ignore_errors=True)
        ws.mkdir(parents=True)
        self.session = Session(task["session_id"], kind, name, ws)
        text = f"ready: {kind} {name} (new)"
        if subj.get("version"):
            if "spec" not in (task.get("inputs") or {}):
                self._drop_session()
                return _error("the subject has a version but no spec input to hydrate from")
            raw = self._fetch_input(task, "spec").read_bytes()
            try:
                spec = json.loads(raw)
            except ValueError as e:
                self._drop_session()
                return _error(f"the subject's spec isn't JSON: {e}")
            rep = self._call(task, {"op": "hydrate", "kind": kind, "name": name, "spec": spec,
                                    "note": f"hydrated from library version {subj['version']}"})
            if not rep.get("ok"):
                self._drop_session()
                return _error(f"hydrating {name}: {rep.get('error')}")
            text = f"ready: {rep['text']} (from version {subj['version']})"
        return {"status": "ok", "content": [{"type": "text", "text": text}]}

    def _drop_session(self):
        s, self.session = self.session, None
        if s is None:
            return
        if s.worker is not None:
            s.worker.kill()
        shutil.rmtree(s.ws, ignore_errors=True)

    # -- inputs and outputs

    def _fetch_input(self, task: dict, arg: str) -> Path:
        inp = (task.get("inputs") or {}).get(arg)
        if not inp:
            raise ValueError(f"no input for {arg!r} (a library version id)")
        data = self.dept.get_bytes(inp["url"])
        sha = hashlib.sha256(data).hexdigest()
        if inp.get("sha256") and sha != inp["sha256"]:
            raise ValueError(f"input {arg}: sha256 mismatch ({sha} != {inp['sha256']})")
        fname = Path(inp.get("filename") or arg).name
        fname = re.sub(r"[^A-Za-z0-9_.\-]", "_", fname) or arg
        d = self.session.ws / "_artist" / "inputs"
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{sha[:16]}_{fname}"
        p.write_bytes(data)
        return p

    def put_blob(self, data: bytes, mime: str) -> str:
        sha = hashlib.sha256(data).hexdigest()
        if sha not in self.uploaded:
            self.dept.request("PUT", f"/v1/runners/{self.runner_id}/blobs/{sha}", raw=data, ctype=mime,
                              timeout=600)
            self.uploaded.add(sha)
        return sha

    def _content(self, items: list[dict]) -> tuple[list[dict], list | None]:
        out, questions = [], None
        for it in items:
            if it["type"] == "image":
                sha = self.put_blob(Path(it["path"]).read_bytes(), it["mime"])
                out.append({"type": "image", "blob": sha, "mime": it["mime"]})
            else:  # the session's scratch paths in a tool's text say nothing useful off this machine
                text = it["text"].replace(str(self.session.ws / "_artist" / "out"), "<scratch>")
                out.append({"type": "text", "text": text.replace(str(self.session.ws), "<workspace>")})
                q = _questions(it["text"])
                if q is not None:
                    questions = q
        return out, questions

    def _files(self, d: Path) -> list[dict]:
        files = []
        for p in sorted(d.rglob("*")):
            if not p.is_file():
                continue
            mime = _mime(p)
            files.append({"role": _role(p, self.session.name), "filename": str(p.relative_to(d)),
                          "blob": self.put_blob(p.read_bytes(), mime), "mime": mime})
        return files

    def _spec_path(self) -> Path:
        s = self.session
        return (s.ws / "terrain" / s.name if s.kind == "terrain" else s.ws / s.name) / "spec.json"

    def _spec_file(self) -> dict:
        p = self._spec_path()
        if not p.exists():
            raise ValueError(f"{self.session.name} has no spec yet")
        return {"role": "spec", "filename": "spec.json", "blob": self.put_blob(p.read_bytes(), "application/json"),
                "mime": "application/json"}

    def _snapshot(self, task: dict, look: bool) -> dict:
        s = self.session
        if not self._spec_path().exists():
            return _error(f"nothing to snapshot: {s.kind} {s.name} has no spec yet")
        spec_file = self._spec_file()
        content = [{"type": "text", "text": f"snapshot of {s.kind} {s.name}"}]
        if look:
            out = s.ws / "_artist" / "out" / _safe(task["task_id"])
            shutil.rmtree(out, ignore_errors=True)
            if s.kind == "terrain":
                req = {"op": "call", "tool": "look_terrain", "args": {"name": s.name, "map": True, "size": 800}}
            else:
                req = {"op": "call", "tool": "look",
                       "args": {"name": s.name, "paint": False, "size": 384, "resolution": 128}}
            rep = self._call(task, {**req, "out": str(out / "content")})
            if rep.get("ok"):
                imgs, _ = self._content([c for c in rep["content"] if c["type"] == "image"])
                content += imgs
            else:
                content.append({"type": "text", "text": f"(no look: {rep.get('error')})"})
        return {"status": "ok", "content": content, "files": [spec_file]}


def _error(message: str, retryable: bool = False) -> dict:
    return {"status": "error", "content": [], "error": {"message": message, "retryable": retryable}}


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_\-]", "_", s)


def _questions(text: str):
    """Questions for the designer (terrain tools return them as JSON, possibly after a "saved ..." line)."""
    if "questions for the designer" not in text:
        return None
    i = text.find("{")
    while i >= 0:
        try:
            d = json.loads(text[i:])
        except ValueError:
            i = text.find("{", i + 1)
            continue
        if isinstance(d, dict) and d.get("status") == "questions for the designer":
            return d.get("questions") or []
        return None
    return None


MAPS = ("basecolor", "normal", "roughness", "metallic", "specular_gltf", "specular", "ao", "orm", "height")
MIMES = {".glb": "model/gltf-binary", ".gltf": "model/gltf+json", ".fbx": "application/octet-stream",
         ".obj": "model/obj", ".json": "application/json", ".png": "image/png", ".npy": "application/octet-stream",
         ".raw": "application/octet-stream", ".csv": "text/csv", ".bin": "application/octet-stream",
         ".jpg": "image/jpeg", ".exr": "image/x-exr"}


def _mime(p: Path) -> str:
    return MIMES.get(p.suffix.lower(), "application/octet-stream")


def _role(p: Path, name: str) -> str:
    ext = p.suffix.lower().lstrip(".")
    if ext == "png":
        for m in MAPS:
            if p.stem.endswith("_" + m) or p.stem == m:
                return m
        return "png"
    return ext or "file"


def artist_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        v = version("hifipushie")
    except PackageNotFoundError:
        v = "?"
    from .artist_update import running_sha
    sha = running_sha()[:12]
    return f"hifipushie {v}" + (f" (git {sha})" if sha else "")


def equipment(work_root: Path) -> dict:
    ram = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                ram = round(int(line.split()[1]) / 1024 ** 2, 1)
    except OSError:
        pass
    gpu = None
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, timeout=10)
            first = r.stdout.strip().splitlines()[0].split(",")
            gpu = {"name": first[0].strip(), "vram_gb": round(float(first[1]) / 1024, 1)}
        except (OSError, subprocess.SubprocessError, IndexError, ValueError):
            pass
    blender = None
    try:
        from .render import BLENDER as BL
        r = subprocess.run([BL, "--version"], capture_output=True, text=True, timeout=30)
        m = re.search(r"Blender (\S+)", r.stdout)
        blender = m.group(1) if m else None
    except (OSError, subprocess.SubprocessError):
        pass
    work_root.mkdir(parents=True, exist_ok=True)
    return {"cpus": os.cpu_count(), "ram_gb": ram, "gpu": gpu, "blender": blender,
            "disk_gb_free": round(shutil.disk_usage(work_root).free / 1024 ** 3, 1),
            "os": platform.platform()}


SOFTWARE_GL = ("llvmpipe", "softpipe", "swrast", "lavapipe", "software rasterizer")


def gpu_probe(timeout: float = 300.0, blender: str | None = None) -> dict:
    """Can this box's Blender render headless? A 64 px cube in Workbench (clay looks) and EEVEE (painted looks),
    run the way hifipushie runs Blender. {"workbench": "ok" | why, "eevee": "ok" | why, "renderer", "backend", ...}.
    EEVEE on a software rasterizer (Mesa llvmpipe: no usable GPU) counts as unavailable: painted looks would take
    minutes."""
    import tempfile
    from .render import BLENDER
    BL = blender or BLENDER
    script = Path(__file__).with_name("blender_probe.py")
    with tempfile.TemporaryDirectory(prefix="hifipushie-probe-") as tmp:
        try:
            r = subprocess.run([BL, "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script),
                                "--", tmp], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.SubprocessError) as e:
            why = f"blender didn't run: {e}"[:300]
            return {"workbench": why, "eevee": why}
    line = next((l for l in r.stdout.splitlines() if l.startswith("@@probe ")), None)
    if line is None:
        tail = " ".join((r.stdout + r.stderr).strip().splitlines()[-4:])
        why = f"blender exited {r.returncode} without a result: {tail}"[:500]
        return {"workbench": why, "eevee": why}
    res = json.loads(line[len("@@probe "):])
    renderer = (res.get("renderer") or "").lower()
    if res.get("eevee") == "ok" and any(s in renderer for s in SOFTWARE_GL):
        res["eevee"] = f"software rendering only ({res.get('renderer')}): no usable GPU for EEVEE"
    return res


def gpu_note(gpu: dict | None) -> str:
    """What the department/LLM must know when this box can't render painted looks (empty when it can)."""
    if gpu is None or gpu.get("eevee") == "ok":
        return ""
    note = (f"\nTHIS BOX HAS NO EEVEE ({gpu['eevee']}): painted looks are unavailable here. look with paint=true "
            "(the default, shading clay/flat) and style_check with colours=true (the default) will fail or crawl; "
            "use look(paint=false) or shading raking/curvature, and style_check(colours=false).")
    if gpu.get("workbench") != "ok":
        note += f" Clay looks are unavailable too (Workbench: {gpu['workbench']}): no look renders on this box."
    return note


COMMANDS = ("run", "setup", "login", "logout", "install", "uninstall", "status", "probe")


def run_parser(prog: str = "hifipushie-artist") -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=prog, description=__doc__.split("\n\n")[0],
                                 epilog="other commands: " + ", ".join(COMMANDS[1:]) + " (hifipushie-artist <command> -h)")
    ap.add_argument("--mode", choices=("local", "hosted"), default=os.environ.get("OXIDEGEN_RUNNER_MODE") or "local",
                    help="local (default; your machine) or hosted (a department-rented box: config from env only, "
                         "OXIDEGEN_RUNNER_MODE)")
    ap.add_argument("--url", default=None, help="the department (OXIDEGEN_URL, else the saved one, else "
                                                f"{DEFAULT_URL})")
    ap.add_argument("--token", default=None, help="runner token (default $OXIDEGEN_RUNNER_TOKEN, else --token-file)")
    ap.add_argument("--token-file", default=None, help="default ~/.config/hifipushie/runner-token")
    ap.add_argument("--name", default=None, help="runner name, stable per machine (default: the saved one, else the "
                                                 "hostname)")
    ap.add_argument("--work-root", default=None, help="session workspaces live under here (HIFIPUSHIE_ARTIST_WORK, "
                                                      "default ~/.cache/hifipushie-artist)")
    ap.add_argument("--assets", default=None, help="third-party asset packs (default $HIFIPUSHIE_ASSETS, else "
                                                   "./workspace/_templates or $HIFIPUSHIE_HOME/_templates)")
    ap.add_argument("--dir", default=None, help="the runner's directory from `setup` (<project>/.oxidegen/runner: "
                                                "config, token, logs, workspaces; OXIDEGEN_RUNNER_DIR)")
    ap.add_argument("--capabilities", action="store_true", help="print the capabilities and exit")
    ap.add_argument("-v", "--verbose", action="store_true")
    return ap


def _logging(verbose: bool = False):
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, stream=sys.stdout,
                        format="%(asctime)s %(levelname)s %(message)s")


def local_config(a) -> Config:
    """A local runner's config: flags, then env, then what `setup` saved (runner.json), then defaults."""
    saved = saved_settings()
    url = a.url or os.environ.get("OXIDEGEN_URL") or saved.get("url") or DEFAULT_URL
    name = a.name or os.environ.get("HIFIPUSHIE_ARTIST_NAME") or saved.get("name") or socket.gethostname()
    d = runner_dir()
    work = a.work_root or os.environ.get("HIFIPUSHIE_ARTIST_WORK") or (d / "work" if d else
                                                                      "~/.cache/hifipushie-artist")
    from .artist_update import Updater
    return Config(url=url, token=_token(a.token, a.token_file), name=name, work_root=Path(work).expanduser(),
                  assets=a.assets or saved.get("assets") or _assets_default(),
                  updater=Updater.for_this_install(d, saved.get("git_repo") or ""))


RUNNER_DIR: Path | None = None  # a runner set up by `setup` (<project>/.oxidegen/runner): its config, token, state


def runner_dir() -> Path | None:
    if RUNNER_DIR is not None:
        return RUNNER_DIR
    d = os.environ.get("OXIDEGEN_RUNNER_DIR")
    return Path(d).expanduser().resolve() if d else None


def config_dir() -> Path:
    return runner_dir() or Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "hifipushie"


def token_path() -> Path:
    d = runner_dir()
    return d / "token" if d else config_dir() / "runner-token"


def status_path() -> Path:
    """The runner's own last state (`setup` waits on it): <runner dir>/status.json, else
    $XDG_STATE_HOME/hifipushie/runner-status.json."""
    if runner_dir():
        return runner_dir() / "status.json"
    return Path(os.environ.get("XDG_STATE_HOME") or "~/.local/state").expanduser() / "hifipushie" / "runner-status.json"


def write_status(d: dict) -> None:
    try:
        p = status_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(d))
        tmp.replace(p)
    except OSError as e:
        log.debug("status file: %s", e)


def saved_settings() -> dict:
    try:
        return json.loads((config_dir() / "runner.json").read_text())
    except (OSError, ValueError):
        return {}


def main(argv: list[str] | None = None):
    global RUNNER_DIR
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] == "probe":  # (the update check runs it: Blender renders with this version)
        print(json.dumps(gpu_probe()))
        return
    if argv and argv[0] in COMMANDS[1:]:
        from . import artist_setup
        sys.exit(artist_setup.main(argv))
    if argv and argv[0] == "run":
        argv = argv[1:]
    a = run_parser().parse_args(argv)
    if a.dir:
        RUNNER_DIR = Path(a.dir).expanduser().resolve()
    _logging(a.verbose)
    if a.capabilities:
        caps, left = capabilities()
        print(json.dumps({"capabilities": caps, "left_out": left}, indent=1))
        return
    if a.mode == "hosted":
        try:
            cfg = hosted_config()
        except ValueError as e:
            log.error("%s", e)
            sys.exit(2)
        for flag in ("url", "token", "token_file", "name", "work_root"):
            if getattr(a, flag):
                log.warning("hosted mode takes its config from the environment: --%s ignored", flag.replace("_", "-"))
        cfg.update_failed = hosted_start_update(cfg)
    else:
        cfg = local_config(a)
        if not cfg.token:
            log.error("no runner token (none in OXIDEGEN_RUNNER_TOKEN or %s). %s", token_path(), DISCONNECTED)
            sys.exit(EXIT_UNAUTHORIZED)
    if not cfg.assets:
        log.warning("no asset packs found (GNM, MakeHuman): bases with heads/bodies from them will fail; "
                    "pass --assets or set HIFIPUSHIE_ASSETS")
    log.info("hifipushie-artist (%s, %s mode) -> %s as %s", artist_version(), cfg.mode, cfg.url, cfg.name)
    runner = Runner(cfg)
    signal.signal(signal.SIGTERM, lambda *_: runner.stop.set())
    try:
        runner.run()
    except KeyboardInterrupt:
        runner.shutdown()
    if runner.exit_code == EXIT_UNAUTHORIZED:
        if cfg.mode == "local":
            log.error(DISCONNECTED)
            print(DISCONNECTED, file=sys.stderr)
        sys.exit(EXIT_UNAUTHORIZED)


def hosted_start_update(cfg: Config) -> str | None:
    """A hosted box runs the department's pinned sha (OXIDEGEN_WANTED_VERSION) if it differs from the baked one:
    installed over a copy of the image's venv and run as a child. Returns None when there's nothing to do; when
    the child ran, exits with its code; when the update failed (install, check, or no registration within 60 s),
    returns the failed sha so the baked version runs and reports it."""
    from . import artist_update as U
    want = os.environ.get("OXIDEGEN_WANTED_VERSION", "").strip()
    if not want or os.environ.get("OXIDEGEN_UPDATE_CHILD") or U.same(want, U.running_sha()):
        return None
    repo = os.environ.get("OXIDEGEN_WANTED_REPO") or U.DEFAULT_REPO
    log.info("the department wants %s (baked %s): installing it", want[:12], U.running_sha()[:12])
    py, why = U.hosted_update(want, repo, cfg.work_root)
    if py is None:
        log.error("update to %s failed: %s; running the baked version", want[:12], why)
        return want
    started = time.time()
    child = subprocess.Popen([str(py), "-m", "hifipushie.artist"], env={**os.environ, "OXIDEGEN_UPDATE_CHILD": "1"})
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    registered = False
    while child.poll() is None:
        if not registered:
            try:
                st = json.loads(status_path().read_text())
                registered = st.get("state") == "registered" and st.get("at", 0) >= started
            except (OSError, ValueError):
                pass
            if not registered and time.time() - started > U.CONFIRM_SECS + 30:  # (+ its own GPU probe)
                log.error("%s didn't register in time: stopping it, running the baked version", want[:12])
                child.terminate()
                try:
                    child.wait(30)
                except subprocess.TimeoutExpired:
                    child.kill()
                return want
        time.sleep(0.5)
    if child.returncode == EXIT_UNAUTHORIZED or registered:
        sys.exit(child.returncode)
    log.error("%s exited %s before registering; running the baked version", want[:12], child.returncode)
    return want


if __name__ == "__main__":
    main()
