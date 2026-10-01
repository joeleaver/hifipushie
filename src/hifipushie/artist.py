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

# ---------------------------------------------------------------------------------------------- capabilities

FAST = {"guide", "kit_reference", "get_model", "put_model", "edit_model", "history", "revert", "measure",
        "clearance", "set_reference", "set_plan", "check"}
SLOW = {  # (documentation: anything not fast or very_slow is slow, new tools included)
    "look", "compare", "fit", "rig", "style_check", "sync", "set_terrain", "check_terrain", "export", "snapshot"}
VERY_SLOW = {"export_asset", "look_terrain", "export_terrain"}
MUTATES = {"put_model", "edit_model", "revert", "set_plan", "fit", "set_reference", "set_terrain", "sync",
           "terrain_history"}  # terrain_history: only with revert_to, but it can
BLENDER = {"look", "rig", "style_check", "sync", "export_asset", "look_terrain", "export_terrain", "snapshot"}
NO_BLENDER = FAST | {"compare", "fit", "set_terrain", "check_terrain", "export", "terrain_history"}
IMAGES = {"look", "set_reference", "compare", "fit", "set_plan", "check", "rig", "export_asset", "look_terrain",
          "snapshot"}
FILES = {"export", "export_asset", "export_terrain", "snapshot"}

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


def _token(arg: str | None, token_file: str | None) -> str:
    if arg:
        return arg.strip()
    if os.environ.get("OXIDEGEN_RUNNER_TOKEN"):
        return os.environ["OXIDEGEN_RUNNER_TOKEN"].strip()
    p = Path(token_file or "~/.config/hifipushie/runner-token").expanduser()
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


class Department:
    def __init__(self, url: str, token: str):
        self.base = url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, body=None, raw: bytes | None = None, ctype: str | None = None,
                timeout: float = 30.0):
        url = path if path.startswith(("http://", "https://")) else self.base + path
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(url, data=data, method=method)
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
        self.cap_of = {c["tool"]: c for c in self.caps}
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
        body = {"name": self.cfg.name, "artist": ARTIST, "artist_version": artist_version(), "contract": CONTRACT,
                "mode": self.cfg.mode, "equipment": equipment(self.cfg.work_root), "capabilities": self.caps,
                "instructions": instructions()}
        r = self.dept.request("POST", "/v1/runners/register", body)
        self.runner_id = r["runner_id"]
        self.heartbeat_secs = float(r.get("heartbeat_secs") or 15)
        self.poll_secs = float(r.get("poll_secs") or 25)
        self.need_register.clear()
        self.uploaded.clear()
        if self.session:  # re-registering ends the department's side of it ("runner_restarted")
            log.info("re-registered: dropping session %s", self.session.id)
            self._drop_session()
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
            try:
                r = self.dept.request("POST", f"/v1/runners/{rid}/heartbeat", body) or {}
            except HTTPError as e:
                if e.status in (401, 404):
                    self.need_register.set()
                log.warning("heartbeat: %s", e)
                continue
            except OSError as e:
                log.warning("heartbeat: %s", e)
                continue
            with self.lock:
                self.cancels |= set(r.get("cancel") or [])

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
            except HTTPError as e:
                if e.status in (401, 404):
                    log.warning("department forgot this runner (%s): registering again", e.status)
                    self.need_register.set()
                else:
                    log.warning("next: %s", e)
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue
            except OSError as e:
                log.warning("department unreachable: %s", e)
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60)
                continue
            if task:
                self.handle(task)
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
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        sha = ""
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


def main(argv: list[str] | None = None):
    ap = argparse.ArgumentParser(prog="hifipushie-artist", description=__doc__.split("\n\n")[0])
    ap.add_argument("--url", default=os.environ.get("OXIDEGEN_URL", DEFAULT_URL), help="the department (OXIDEGEN_URL)")
    ap.add_argument("--token", default=None, help="runner token (default $OXIDEGEN_RUNNER_TOKEN, else --token-file)")
    ap.add_argument("--token-file", default=None, help="default ~/.config/hifipushie/runner-token")
    ap.add_argument("--name", default=os.environ.get("HIFIPUSHIE_ARTIST_NAME") or socket.gethostname(),
                    help="runner name, stable per machine (default: hostname)")
    ap.add_argument("--work-root", default=os.environ.get("HIFIPUSHIE_ARTIST_WORK")
                    or "~/.cache/hifipushie-artist", help="session workspaces live under here")
    ap.add_argument("--assets", default=None, help="third-party asset packs (default $HIFIPUSHIE_ASSETS, else "
                                                   "./workspace/_templates or $HIFIPUSHIE_HOME/_templates)")
    ap.add_argument("--capabilities", action="store_true", help="print the capabilities and exit")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    if a.capabilities:
        caps, left = capabilities()
        print(json.dumps({"capabilities": caps, "left_out": left}, indent=1))
        return
    token = _token(a.token, a.token_file)
    if not token:
        sys.exit("no runner token: set OXIDEGEN_RUNNER_TOKEN or write it to ~/.config/hifipushie/runner-token "
                 "(mint one under Account -> Tokens in oxidegen)")
    cfg = Config(url=a.url, token=token, name=a.name, work_root=Path(a.work_root).expanduser(),
                 assets=a.assets or _assets_default())
    if not cfg.assets:
        log.warning("no asset packs found (GNM, MakeHuman): bases with heads/bodies from them will fail; "
                    "pass --assets or set HIFIPUSHIE_ASSETS")
    runner = Runner(cfg)
    signal.signal(signal.SIGTERM, lambda *_: runner.stop.set())
    try:
        runner.run()
    except KeyboardInterrupt:
        runner.shutdown()


if __name__ == "__main__":
    main()
