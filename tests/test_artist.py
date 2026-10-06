"""The oxidegen artist runner (hifipushie.artist) against a fake department (artist/1, contract §10.1).

Run: uv run pytest tests/test_artist.py
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

os.environ["HIFIPUSHIE_HOME"] = tempfile.mkdtemp(prefix="hp_artist_")
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="hp_artist_state_")  # the runner's status file
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="hp_artist_config_")  # token file, saved settings
TESTS = Path(__file__).parent
sys.path.insert(0, str(TESTS))
os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, [str(TESTS), os.environ.get("PYTHONPATH")]))

from hifipushie import artist  # noqa: E402

TOKEN = "test-token"


def small_spec() -> dict:
    return {
        "joints": {"pelvis": {"pos": [0, 0, 0.5], "r": 0.1}, "chest": {"pos": [0, 0, 0.8], "r": 0.12},
                   "head": {"pos": [0, 0, 1.0], "r": 0.1}},
        "bones": {"spine": {"a": "pelvis", "b": "chest"}, "neck": {"a": "chest", "b": "head"}},
        "blobs": {"skull": {"at": "head", "size": [0.1, 0.11, 0.12]}},
    }


# ------------------------------------------------------------------------------------------- fake department

class FakeDepartment:
    """Just enough of oxidegen's runner side (§10.1): register, heartbeat, next (long-poll), blobs, progress, result."""

    def __init__(self):
        self.tasks: queue.Queue = queue.Queue()
        self.results: dict[str, dict] = {}
        self.result_events: dict[str, threading.Event] = {}
        self.blobs: dict[str, bytes] = {}
        self.progress: list[tuple[str, dict]] = []
        self.heartbeats: list[dict] = []
        self.registrations: list[dict] = []
        self.cancel: set[str] = set()
        self.cancel_on_progress: set[str] = set()  # told only in the progress reply, not the heartbeat
        self.runner_id = None
        self.wanted_version = None  # returned in register/heartbeat replies (runner self-update)
        # public routes (pairing, the install manifest, downloads): see artist_setup
        self.pairing = "approve"  # | "deny" | "expire" | "pending"
        self.polls = 0
        self.codes: dict[str, str] = {}  # one-time code -> token
        self.install: dict = {}
        self.files: dict[str, bytes] = {}  # GET /files/<name>
        dept = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body=None, raw=None, ctype="application/json"):
                data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
                self.send_response(code)
                if data:
                    self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def _authed(self):
                if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                    self._send(401, {"error": "bad token"})
                    return False
                return True

            def do_GET(self):
                if self.path == "/v1/artists/sculpt/install":
                    return self._send(200, dept.install)
                if self.path.startswith("/files/") and self.path[7:] in dept.files:
                    return self._send(200, raw=dept.files[self.path[7:]], ctype="application/octet-stream")
                if not self._authed():
                    return
                if self.path.startswith("/v1/blobs/"):
                    sha = self.path.rsplit("/", 1)[1]
                    if sha in dept.blobs:
                        return self._send(200, raw=dept.blobs[sha], ctype="application/octet-stream")
                return self._send(404, {"error": "no such blob"})

            def do_PUT(self):
                if not self._authed():
                    return
                parts = self.path.strip("/").split("/")  # v1 runners {id} blobs {sha}
                data = self._body()
                if len(parts) != 5 or parts[3] != "blobs" or parts[2] != dept.runner_id:
                    return self._send(404, {"error": "no route"})
                if hashlib.sha256(data).hexdigest() != parts[4]:
                    return self._send(400, {"error": "sha256 mismatch"})
                dept.blobs[parts[4]] = data
                return self._send(204)

            def do_POST(self):
                if self.path.startswith("/v1/runner-pairings"):
                    return self._pairing(json.loads(self._body() or b"{}"))
                if not self._authed():
                    return
                body = json.loads(self._body() or b"{}")
                p = self.path.strip("/").split("/")
                if p == ["v1", "runners", "register"]:
                    dept.registrations.append(body)
                    dept.runner_id = str(uuid.uuid4())
                    return self._send(200, {"runner_id": dept.runner_id, "heartbeat_secs": 0.3, "poll_secs": 0.5,
                                            "wanted_version": dept.wanted_version})
                if len(p) == 4 and p[:2] == ["v1", "runners"]:
                    if p[2] != dept.runner_id:
                        return self._send(404, {"error": "no such runner"})
                    if p[3] == "heartbeat":
                        dept.heartbeats.append(body)
                        return self._send(200, {"cancel": sorted(dept.cancel), "wanted_version": dept.wanted_version})
                    if p[3] == "next":
                        try:
                            return self._send(200, dept.tasks.get(timeout=0.5))
                        except queue.Empty:
                            return self._send(204)
                if len(p) == 4 and p[:2] == ["v1", "tasks"]:
                    tid = p[2]
                    if p[3] == "progress":
                        dept.progress.append((tid, body))
                        return self._send(200, {"cancel": tid in dept.cancel or tid in dept.cancel_on_progress})
                    if p[3] == "result":
                        if tid in dept.results:
                            return self._send(409, {"error": "already finished"})
                        dept.results[tid] = body
                        dept.result_events.setdefault(tid, threading.Event()).set()
                        return self._send(204)
                return self._send(404, {"error": "no route"})

            def _pairing(self, body):
                if self.path == "/v1/runner-pairings":
                    assert body["artist"] == "sculpt" and body["name"] and body["hostname"]
                    return self._send(200, {"pairing_id": "pr1", "device_secret": "sec", "user_code": "WDJB-MJHT",
                                            "verify_url": dept.url + "/pair/WDJB-MJHT", "expires_in": 5,
                                            "poll_secs": 0.05})
                if self.path == "/v1/runner-pairings/poll":
                    assert body == {"pairing_id": "pr1", "device_secret": "sec"}
                    dept.polls += 1
                    if dept.polls < 3 or dept.pairing == "pending":
                        return self._send(202, {"status": "pending"})
                    if dept.pairing == "approve":
                        return self._send(200, {"status": "approved", "token": TOKEN})
                    return self._send(410, {"status": "denied" if dept.pairing == "deny" else "expired"})
                if self.path == "/v1/runner-pairings/redeem":
                    tok = dept.codes.pop(body.get("code"), None)
                    if tok is None:
                        return self._send(410, {"error": "unknown or used code"})
                    return self._send(200, {"token": tok})
                return self._send(404, {"error": "no route"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def put_blob(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        self.blobs[sha] = data
        return sha

    def submit(self, session: str, tool: str, args: dict | None = None, inputs: dict | None = None) -> str:
        tid = str(uuid.uuid4())
        self.result_events.setdefault(tid, threading.Event())
        self.tasks.put({"task_id": tid, "session_id": session, "project_id": "p1", "tool": tool, "args": args or {},
                        "inputs": inputs or {}, "deadline_secs": 600})
        return tid

    def wait(self, tid: str, timeout: float = 120) -> dict:
        assert self.result_events[tid].wait(timeout), f"no result for {tid}"
        return self.results[tid]

    def run(self, session, tool, args=None, inputs=None, timeout=120) -> dict:
        return self.wait(self.submit(session, tool, args, inputs), timeout)


def text_of(res: dict) -> str:
    return "\n".join(c["text"] for c in res["content"] if c["type"] == "text")


@pytest.fixture(scope="module")
def dept_runner():
    dept = FakeDepartment()
    root = Path(tempfile.mkdtemp(prefix="hp_artist_work_"))
    cfg = artist.Config(url=dept.url, token=TOKEN, name="test-box", work_root=root, preload=["artist_test_tools"])
    runner = artist.Runner(cfg)
    runner.progress_secs = 0.5
    t = threading.Thread(target=runner.run, daemon=True)
    t.start()
    deadline = time.time() + 30
    while not dept.registrations and time.time() < deadline:
        time.sleep(0.05)
    yield dept, runner, root
    runner.stop.set()
    t.join(10)
    dept.server.shutdown()


# ------------------------------------------------------------------------------------------- the protocol

def test_session_lifecycle(dept_runner):
    dept, runner, root = dept_runner
    reg = dept.registrations[0]
    assert reg["artist"] == "sculpt" and reg["contract"] == "artist/1" and reg["mode"] == "local"
    assert reg["name"] == "test-box" and reg["artist_version"].startswith("hifipushie ")
    assert {"cpus", "ram_gb", "blender", "disk_gb_free"} <= set(reg["equipment"])
    tools = {c["tool"]: c for c in reg["capabilities"]}
    assert "nap" in tools and tools["nap"]["timing"] == "slow"  # a new tool shows up by itself, default slow
    assert "snapshot" in tools and "list_models" not in tools

    # _open hydrates the subject from its spec version
    spec = {**small_spec(), "story": {"age": "old"}}
    sha = dept.put_blob(json.dumps(spec).encode())
    sid = "sess-1"
    res = dept.run(sid, "_open", {"subject": {"kind": "model", "name": "hero", "version": "ver-1"}, "workspace": sid},
                   {"spec": {"version": "ver-1", "role": "spec", "filename": "spec.json", "sha256": sha,
                             "url": f"/v1/blobs/{sha}"}})
    assert res["status"] == "ok", res
    assert "ready" in text_of(res) and "ver-1" in text_of(res)
    ws = root / sid
    stored = json.loads((ws / "hero" / "spec.json").read_text())
    assert stored["joints"] == spec["joints"] and stored["story"] == {"age": "old"}

    # tools run in the session's worker, with the subject's name injected
    res = dept.run(sid, "put_model", {"spec": small_spec(), "note": "from the department"})
    assert res["status"] == "ok", res
    assert "saved hero v2" in text_of(res)
    res = dept.run(sid, "get_model")
    assert res["status"] == "ok" and '"skull"' in text_of(res)
    assert "story" not in json.loads((ws / "hero" / "spec.json").read_text())
    res = dept.run(sid, "history")
    assert "hydrated from library version ver-1" in text_of(res) and "from the department" in text_of(res)

    # the tool's own error text comes back as an error result
    res = dept.run(sid, "measure", {"along": "no_such_bone"})
    assert res["status"] == "error" and "no_such_bone" in res["error"]["message"], res
    assert res["error"]["retryable"] is False

    # snapshot: the spec as a blob, uploaded and verified by sha
    res = dept.run(sid, "snapshot", {"look": False})
    assert res["status"] == "ok", res
    (f,) = res["files"]
    assert f["role"] == "spec" and f["filename"] == "spec.json"
    data = dept.blobs[f["blob"]]
    assert hashlib.sha256(data).hexdigest() == f["blob"]
    assert json.loads(data) == json.loads((ws / "hero" / "spec.json").read_text())

    # export: the OBJ goes back as a file, with the spec
    res = dept.run(sid, "export", {"resolution": 48})
    assert res["status"] == "ok", res
    roles = {f["role"]: f for f in res["files"]}
    assert set(roles) == {"obj", "spec"} and roles["obj"]["filename"] == "hero.obj"
    assert dept.blobs[roles["obj"]["blob"]].startswith(b"# hifipushie hero")
    assert str(ws) not in text_of(res)  # host paths in the text are rewritten

    # confinement and subject kinds, refused by the runner itself
    res = dept.run(sid, "look", {"save": "/tmp/x.png"})
    assert res["status"] == "error" and "unknown argument" in res["error"]["message"]
    res = dept.run(sid, "look", {"matcap": "../../../etc/passwd"})
    assert res["status"] == "error" and "matcap" in res["error"]["message"]
    res = dept.run(sid, "set_terrain", {"patch": {}})
    assert res["status"] == "error" and "terrain" in res["error"]["message"]
    res = dept.run(sid, "list_models")
    assert res["status"] == "error" and "no tool" in res["error"]["message"]
    res = dept.run("other-session", "get_model")
    assert res["status"] == "error" and "isn't open" in res["error"]["message"]

    # cancel: kill the worker's whole process group (its child too), report canceled
    tid = dept.submit(sid, "nap", {"secs": 120})
    pids_f = ws / "nap.pids"
    deadline = time.time() + 60
    while not pids_f.exists() and time.time() < deadline:
        time.sleep(0.1)
    worker_pid, child_pid = map(int, pids_f.read_text().split())
    time.sleep(1.2)  # a progress post or two, from progress.log
    assert any(t == tid and b["message"] == "napping 2/2" for t, b in dept.progress), dept.progress
    assert any(h.get("task") == tid for h in dept.heartbeats)
    dept.cancel.add(tid)
    res = dept.wait(tid, 30)
    assert res["status"] == "canceled", res
    dept.cancel.discard(tid)
    assert not _alive(worker_pid) and not _alive(child_pid)

    # the next task gets a fresh worker
    res = dept.run(sid, "get_model")
    assert res["status"] == "ok" and '"skull"' in text_of(res)

    # _close drops the workspace
    res = dept.run(sid, "_close")
    assert res["status"] == "ok"
    deadline = time.time() + 10
    while ws.exists() and time.time() < deadline:
        time.sleep(0.05)
    assert not ws.exists() and runner.session is None


def test_cancel_via_progress_reply_and_terrain_session(dept_runner):
    dept, runner, root = dept_runner
    sid = "sess-2"
    res = dept.run(sid, "_open", {"subject": {"kind": "terrain", "name": "vale", "version": None}, "workspace": sid})
    assert res["status"] == "ok" and "new" in text_of(res)
    res = dept.run(sid, "get_model")
    assert res["status"] == "error" and "model" in res["error"]["message"]
    res = dept.run(sid, "guide", {"topic": "terrain"})  # subject-less tools work for either kind
    assert res["status"] == "ok"
    res = dept.run(sid, "snapshot", {"look": False})
    assert res["status"] == "error" and "no spec yet" in res["error"]["message"]
    res = dept.run(sid, "_close")
    assert res["status"] == "ok" and not (root / sid).exists()

    sid = "sess-2b"
    assert dept.run(sid, "_open", {"subject": {"kind": "model", "name": "m", "version": None},
                                   "workspace": sid})["status"] == "ok"
    tid = dept.submit(sid, "nap", {"secs": 120})
    pids_f = root / sid / "nap.pids"
    deadline = time.time() + 60
    while not pids_f.exists() and time.time() < deadline:
        time.sleep(0.1)
    pids = list(map(int, pids_f.read_text().split()))
    dept.cancel_on_progress.add(tid)
    res = dept.wait(tid, 30)
    assert res["status"] == "canceled" and not any(_alive(p) for p in pids)
    assert dept.run(sid, "_close")["status"] == "ok" and not (root / sid).exists()


def test_reregister_on_404(dept_runner):
    dept, runner, root = dept_runner
    n = len(dept.registrations)
    dept.runner_id = "forgotten"  # the department lost the runner: next/heartbeat now 404
    deadline = time.time() + 15
    while len(dept.registrations) == n and time.time() < deadline:
        time.sleep(0.05)
    assert len(dept.registrations) > n
    res = dept.run("sess-3", "_open", {"subject": {"kind": "model", "name": "again", "version": None},
                                       "workspace": "sess-3"})
    assert res["status"] == "ok"
    assert dept.run("sess-3", "_close")["status"] == "ok"


def _alive(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")


# ------------------------------------------------------------------------------------------- capabilities

def _caps():
    caps, left = artist.capabilities(["artist_test_tools"])
    return {c["tool"]: c for c in caps}, left


def test_capabilities_are_derived_and_confined():
    caps, left = _caps()
    assert set(left) >= {"list_models", "pull"}
    for c in caps.values():
        props = c["input_schema"].get("properties", {})
        assert "name" not in props, c["tool"]
        assert "name" not in c["input_schema"].get("required", []), c["tool"]
        for p, s in props.items():
            assert not artist._host_path_param(p, s), (c["tool"], p)
        assert c["timing"] in ("fast", "slow", "very_slow")
        assert set(c["needs"]) == {"gpu", "blender"} and c["needs"]["gpu"] is False
        assert c["subject_kinds"] and set(c["subject_kinds"]) <= {"model", "terrain"}
        assert artist.re.fullmatch(r"[a-z][a-z0-9_]{0,40}", c["tool"])
    for t in ("look", "set_plan", "check", "rig", "style_check", "export_asset"):
        assert "save" not in caps[t]["input_schema"]["properties"]
    assert "path" not in caps["export"]["input_schema"].get("properties", {})
    assert "out_dir" not in caps["export_asset"]["input_schema"]["properties"]
    assert "out_dir" not in caps["export_terrain"]["input_schema"]["properties"]
    assert caps["clearance"]["input_schema"]["properties"]["path"]  # a polyline, not a host path: kept
    ref = caps["set_reference"]["input_schema"]
    assert "image_path" not in ref["properties"]
    assert ref["properties"]["image"] == {"type": "string", "x-oxidegen": "version",
                                          "description": "a library version id (an image)"}
    assert set(ref["required"]) == {"view", "image"}
    assert caps["look"]["input_schema"]["properties"]["matcap"]["pattern"]
    expect = {"fast": ["guide", "kit_reference", "get_model", "put_model", "edit_model", "history", "revert", "measure",
                       "clearance", "set_reference", "set_plan", "check", "look"],
              "slow": ["compare", "fit", "rig", "style_check", "sync", "set_terrain", "check_terrain", "export",
                       "snapshot", "nap"],
              "very_slow": ["export_asset", "look_terrain", "export_terrain"]}
    for timing, tools in expect.items():
        for t in tools:
            assert caps[t]["timing"] == timing, t
    for t in ("put_model", "edit_model", "revert", "set_plan", "fit", "set_reference", "set_terrain", "sync"):
        assert caps[t]["mutates_subject"], t
    assert not caps["look"]["mutates_subject"] and not caps["get_model"]["mutates_subject"]
    for t in ("look", "export_asset", "look_terrain", "export_terrain", "sync", "rig", "snapshot"):
        assert caps[t]["needs"]["blender"], t
    assert not caps["get_model"]["needs"]["blender"]
    assert caps["set_terrain"]["subject_kinds"] == ["terrain"] and caps["look"]["subject_kinds"] == ["model"]
    assert caps["guide"]["subject_kinds"] == ["model", "terrain"]
    assert caps["terrain_history"]["subject_kinds"] == ["terrain"]
    assert caps["snapshot"]["returns"] == ["text", "image", "file"]


def test_unknown_tools_with_host_paths_or_no_subject_are_left_out():
    class T:
        def __init__(self, name, props, required=()):
            self.name, self.title, self.description = name, None, f"{name} does things."
            self.input_schema = {"type": "object", "properties": props, "required": list(required)}

    cap, why = artist.capability(T("list_everything", {}))
    assert cap is None and "no subject" in why
    cap, why = artist.capability(T("load_mesh", {"name": {"type": "string"}, "mesh_path": {"type": "string"}},
                                   ["name", "mesh_path"]))
    assert cap is None and "host path" in why
    cap, _ = artist.capability(T("bake", {"name": {"type": "string"}, "out_dir": {"anyOf": [{"type": "string"},
                                                                                              {"type": "null"}]},
                                          "level": {"type": "integer"}}, ["name"]))
    assert list(cap["input_schema"]["properties"]) == ["level"] and cap["timing"] == "slow"
    assert cap["needs"]["blender"] is True  # unknown: assume it renders


def test_questions_and_roles():
    q = {"status": "questions for the designer", "why": "w", "questions": [{"id": "a", "question": "?"}]}
    assert artist._questions("saved terrain vale v1\n" + json.dumps(q, indent=1)) == q["questions"]
    assert artist._questions(json.dumps(q)) == q["questions"]
    assert artist._questions("saved terrain vale v1\nall good {not json}") is None
    assert artist._role(Path("hero_basecolor.png"), "hero") == "basecolor"
    assert artist._role(Path("hero_body_orm.png"), "hero") == "orm"
    assert artist._role(Path("hero_specular_gltf.png"), "hero") == "specular_gltf"
    assert artist._role(Path("hero.glb"), "hero") == "glb"
    assert artist._role(Path("hero.fbx"), "hero") == "fbx"
    assert artist._role(Path("hero.json"), "hero") == "json"


# ------------------------------------------------------------------------------------------- confinement in hifipushie

def test_spec_strings_that_become_paths_are_names():
    from hifipushie import paint, retopo, stylesheet
    from hifipushie.spec import SpecError
    for bad in ("../../../etc/passwd", "/abs", "Up_Case", "a/b"):
        with pytest.raises(ValueError):
            stylesheet.load(bad)
    assert stylesheet.load("stylised_realist")
    for bad in ("../x", "0123456789abcdeg", "new/../../x", ""):
        with pytest.raises(SpecError):
            paint.painted_path(bad)
    assert paint.painted_path("0123456789abcdef").name == "0123456789abcdef.npz"
    for bad in ("../../x", "/etc/x", "nope"):
        with pytest.raises(ValueError):
            retopo.load_template(bad)
    assert retopo.load_template("male_stylized")["name"] == "male_stylized"


def test_put_model_rejects_traversal_in_specs():
    from hifipushie import server
    with pytest.raises(Exception, match="style sheet"):
        server.put_model("trav", {**small_spec(), "style": {"sheet": "../../../etc/x"}})
    with pytest.raises(Exception, match="painted"):
        server.put_model("trav2", {**small_spec(), "paint": {"p": {"color": "#ff0000", "painted": "../../x"}}})


def test_live_blender_is_off_in_runner_mode(monkeypatch):
    from hifipushie import scene
    import socket

    def boom(*a, **k):
        raise AssertionError("tried to reach a live Blender")

    monkeypatch.setenv("HIFIPUSHIE_NO_LIVE", "1")
    monkeypatch.setattr(socket, "create_connection", boom)
    assert scene._live_call("result = 1") is None
    assert scene.live_session("anything") is False


@pytest.mark.skipif(not __import__("shutil").which("blender"), reason="needs Blender for the clay look")
def test_snapshot_with_a_look(dept_runner):
    dept, runner, root = dept_runner
    sid = "sess-look"
    assert dept.run(sid, "_open", {"subject": {"kind": "model", "name": "lk", "version": None},
                                   "workspace": sid})["status"] == "ok"
    assert dept.run(sid, "put_model", {"spec": small_spec()})["status"] == "ok"
    res = dept.run(sid, "snapshot", {}, timeout=300)
    assert res["status"] == "ok", res
    (img,) = [c for c in res["content"] if c["type"] == "image"]
    data = dept.blobs[img["blob"]]
    assert img["mime"] == "image/png" and data.startswith(b"\x89PNG") and hashlib.sha256(data).hexdigest() == img["blob"]
    assert [f["role"] for f in res["files"]] == ["spec", "preview"]  # the look is filed too (dailies show WIPs)
    pv = res["files"][1]
    assert pv["blob"] == img["blob"] and pv["mime"] == "image/png" and pv["filename"] == "preview.png"
    assert [f["role"] for f in dept.run(sid, "snapshot", {"look": False})["files"]] == ["spec"]
    assert dept.run(sid, "_close")["status"] == "ok"


def test_open_names_the_library_version_it_started_from(dept_runner):
    """The department's subject.from summary (asset, number, approved or not) is what history and _open say, not a
    bare version id (s0urc3: "hydrated from library version c8fcfcf0..." read like an unrelated asset)."""
    dept, runner, root = dept_runner
    sha = dept.put_blob(json.dumps(small_spec()).encode())
    summary = 'library asset "frame" (model) v2 ver-2 — the latest saved version with a spec; NOT the approved one (v1)'
    res = dept.run("sess-from", "_open", {"subject": {"kind": "model", "name": "frame", "version": "ver-2",
                                                       "from": {"summary": summary}}, "workspace": "sess-from"},
                   {"spec": {"version": "ver-2", "role": "spec", "filename": "spec.json", "sha256": sha,
                             "url": f"/v1/blobs/{sha}"}})
    assert res["status"] == "ok", res
    assert summary in text_of(res)
    assert f"hydrated from {summary}" in text_of(dept.run("sess-from", "history"))


def test_set_reference_takes_a_library_version(dept_runner):
    import io
    from PIL import Image, ImageDraw
    dept, runner, root = dept_runner
    im = Image.new("RGB", (200, 300), "white")
    ImageDraw.Draw(im).ellipse([60, 20, 140, 280], fill="black")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    sha = dept.put_blob(buf.getvalue())
    sid = "sess-ref"
    assert dept.run(sid, "_open", {"subject": {"kind": "model", "name": "rf", "version": None},
                                   "workspace": sid})["status"] == "ok"
    assert dept.run(sid, "put_model", {"spec": small_spec()})["status"] == "ok"
    inp = {"image": {"version": "ver-img", "role": "image", "filename": "../../concept.png", "sha256": sha,
                     "url": f"/v1/blobs/{sha}"}}
    res = dept.run(sid, "set_reference", {"view": "front", "image": "ver-img"}, inp)
    assert res["status"] == "ok", res
    assert "reference front set" in text_of(res) and any(c["type"] == "image" for c in res["content"])
    refs = json.loads((root / sid / "rf" / "refs" / "refs.json").read_text())
    assert refs["front"]["path"].startswith(str(root / sid))
    bad = {"image": {**inp["image"], "sha256": "0" * 64}}
    res = dept.run(sid, "set_reference", {"view": "front", "image": "ver-img"}, bad)
    assert res["status"] == "error" and "sha256" in res["error"]["message"]
    assert dept.run(sid, "_close")["status"] == "ok"


# ------------------------------------------------------------------------------------------- hosted mode

def test_hosted_config_comes_from_env_only(tmp_path, monkeypatch):
    (Path(os.environ["XDG_CONFIG_HOME"]) / "hifipushie").mkdir(parents=True, exist_ok=True)
    artist.token_path().write_text("file-token")  # a token file is never read in hosted mode
    try:
        with pytest.raises(ValueError, match="OXIDEGEN_RUNNER_TOKEN"):
            artist.hosted_config({"OXIDEGEN_URL": "https://dept.example"})
        with pytest.raises(ValueError, match="OXIDEGEN_URL"):
            artist.hosted_config({"OXIDEGEN_RUNNER_TOKEN": "t"})
        cfg = artist.hosted_config({"OXIDEGEN_URL": "https://dept.example", "OXIDEGEN_RUNNER_TOKEN": " tok \n",
                                    "OXIDEGEN_RUNNER_NAME": "hosted-1234", "HIFIPUSHIE_ARTIST_WORK": str(tmp_path),
                                    "HIFIPUSHIE_ASSETS": "/opt/packs"})
        assert (cfg.url, cfg.token, cfg.name, cfg.mode, cfg.probe) == ("https://dept.example", "tok", "hosted-1234",
                                                                        "hosted", True)
        assert cfg.work_root == tmp_path and cfg.assets == "/opt/packs"
        assert artist.hosted_config({"OXIDEGEN_URL": "u", "OXIDEGEN_RUNNER_TOKEN": "t"}).name.startswith("hosted-")
    finally:
        artist.token_path().unlink()


def _wait(cond, secs=30):
    deadline = time.time() + secs
    while not cond() and time.time() < deadline:
        time.sleep(0.05)
    return cond()


def test_hosted_registers_with_the_probe_and_exits_on_a_refused_token(tmp_path, monkeypatch):
    global TOKEN  # (the fake department checks it per request)
    probe = {"workbench": "ok", "eevee": "software rendering only (llvmpipe): no usable GPU for EEVEE",
             "renderer": "llvmpipe (LLVM 20)", "backend": "OPENGL"}
    monkeypatch.setattr(artist, "gpu_probe", lambda timeout=300.0: dict(probe))
    dept = FakeDepartment()
    try:
        env = {"OXIDEGEN_URL": dept.url, "OXIDEGEN_RUNNER_TOKEN": TOKEN, "OXIDEGEN_RUNNER_NAME": "hosted-abc",
               "HIFIPUSHIE_ARTIST_WORK": str(tmp_path)}
        runner = artist.Runner(artist.hosted_config(env))
        t = threading.Thread(target=runner.run, daemon=True)
        t.start()
        assert _wait(lambda: dept.registrations)
        reg = dept.registrations[0]
        assert reg["mode"] == "hosted" and reg["name"] == "hosted-abc"
        eq = reg["equipment"]
        assert eq["eevee"].startswith("software") and eq["workbench"] == "ok" and eq["gpu_renderer"].startswith("llvm")
        assert {"cpus", "ram_gb", "blender", "gpu"} <= set(eq)
        caps = {c["tool"]: c for c in reg["capabilities"]}
        assert caps["look"]["needs"]["gpu"] and caps["style_check"]["needs"]["gpu"]
        assert not caps["get_model"]["needs"]["gpu"] and not caps["export"]["needs"]["gpu"]
        assert "NO EEVEE" in reg["instructions"] and "paint=false" in reg["instructions"]
        # snapshot look=false needs no worker: the department checkpoints every session with it
        sid = "hosted-s"
        assert dept.run(sid, "_open", {"subject": {"kind": "model", "name": "m", "version": None},
                                       "workspace": sid})["status"] == "ok"
        assert dept.run(sid, "put_model", {"spec": small_spec()})["status"] == "ok"
        res = dept.run(sid, "snapshot", {"look": False}, timeout=10)
        assert res["status"] == "ok" and [f["role"] for f in res["files"]] == ["spec"]
        assert dept.run(sid, "_close")["status"] == "ok"

        # the token is revoked: the runner stops (exit code 77), it doesn't retry forever
        old, TOKEN = TOKEN, "revoked"
        try:
            dept.runner_id = "forgotten"  # (next/heartbeat 404 -> re-register -> 401)
            t.join(30)
        finally:
            TOKEN = old
        assert not t.is_alive() and runner.exit_code == artist.EXIT_UNAUTHORIZED
        assert json.loads(artist.status_path().read_text())["state"] == "unauthorized"
    finally:
        dept.server.shutdown()


def test_main_exits_77_on_a_refused_token_and_2_without_config(tmp_path, monkeypatch):
    monkeypatch.setattr(artist, "gpu_probe", lambda timeout=300.0: {"workbench": "ok", "eevee": "ok"})
    dept = FakeDepartment()
    try:
        for k, v in {"OXIDEGEN_URL": dept.url, "OXIDEGEN_RUNNER_TOKEN": "wrong", "OXIDEGEN_RUNNER_MODE": "hosted",
                     "HIFIPUSHIE_ARTIST_WORK": str(tmp_path)}.items():
            monkeypatch.setenv(k, v)
        t0 = time.time()
        with pytest.raises(SystemExit) as e:
            artist.main([])
        assert e.value.code == artist.EXIT_UNAUTHORIZED and time.time() - t0 < 30
        monkeypatch.delenv("OXIDEGEN_RUNNER_TOKEN")
        with pytest.raises(SystemExit) as e:
            artist.main(["--mode", "hosted"])
        assert e.value.code == 2
        # local mode: a refused token says how to reconnect, and exits 77 too
        monkeypatch.setenv("OXIDEGEN_RUNNER_TOKEN", "wrong")
        with pytest.raises(SystemExit) as e:
            artist.main(["--mode", "local", "--url", dept.url, "--work-root", str(tmp_path)])
        assert e.value.code == artist.EXIT_UNAUTHORIZED
    finally:
        dept.server.shutdown()


# ------------------------------------------------------------------------------------------- asset packs

def _fake_manifest(monkeypatch):
    """One required pack of one file, one optional pack (never checked by the runner)."""
    import hashlib
    from hifipushie import assets
    body = b"hand-made weights"
    man = {"makehuman": {"source": "test", "licence": "CC0", "files": [
               {"path": "rigs/default_weights.mhw", "url": "https://example.invalid/w", "sha256": hashlib.sha256(body).hexdigest()}]},
           "rock_scans": {"optional": True, "source": "test", "licence": "CC0", "files": [
               {"path": "rock.jpg", "url": "https://example.invalid/r", "sha256": "0" * 64}]}}
    monkeypatch.setattr(assets, "manifest", lambda: man)
    return assets, body


def test_packs_state_checks_the_required_packs_against_this_versions_manifest(tmp_path, monkeypatch):
    assets, body = _fake_manifest(monkeypatch)
    st = artist.packs_state(None)
    assert st["ok"] is False and "no asset packs directory" in st["problems"]["assets"][0]
    st = artist.packs_state(str(tmp_path))
    assert st == {"ok": False, "problems": {"makehuman": ["missing rigs/default_weights.mhw"]}, "dir": str(tmp_path)}
    f = tmp_path / "makehuman" / "rigs" / "default_weights.mhw"
    f.parent.mkdir(parents=True)
    f.write_bytes(b"an older pack")
    assert artist.packs_state(str(tmp_path))["problems"] == {"makehuman": ["checksum mismatch rigs/default_weights.mhw"]}
    f.write_bytes(body)
    assert artist.packs_state(str(tmp_path)) == {"ok": True, "problems": {}, "dir": str(tmp_path)}  # the optional pack isn't required


def test_a_runner_with_an_outdated_pack_registers_not_ready_refetches_and_registers_again(tmp_path, monkeypatch):
    assets, body = _fake_manifest(monkeypatch)
    fetched = []

    def fake_fetch(names=None, log=print):
        fetched.append(list(names))
        assert _wait(lambda: dept.registrations, 30)  # the runner registers (not ready) while this runs
        f = tmp_path / "packs" / "makehuman" / "rigs" / "default_weights.mhw"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(body)

    dept = FakeDepartment()
    monkeypatch.setattr(assets, "fetch", fake_fetch)
    cfg = artist.Config(url=dept.url, token=TOKEN, name="pack-box", work_root=tmp_path / "work", assets=str(tmp_path / "packs"),
                        preload=["artist_test_tools"])
    runner = artist.Runner(cfg)
    runner.poll_secs = 0.5
    t = threading.Thread(target=runner.run, daemon=True)
    t.start()
    try:
        assert _wait(lambda: len(dept.registrations) >= 2, 40), dept.registrations
        first, last = dept.registrations[0]["equipment"]["packs"], dept.registrations[-1]["equipment"]["packs"]
        assert first == {"ok": False, "problems": {"makehuman": ["missing rigs/default_weights.mhw"]}}
        assert last == {"ok": True, "problems": {}}
        assert fetched == [["makehuman"]]
    finally:
        runner.stop.set()
        t.join(10)
        dept.server.shutdown()


def test_a_failed_refetch_leaves_the_runner_not_ready_and_says_why(tmp_path, monkeypatch):
    assets, _ = _fake_manifest(monkeypatch)

    def no_network(names=None, log=print):
        raise OSError("network is unreachable")

    monkeypatch.setattr(assets, "fetch", no_network)
    cfg = artist.Config(url="http://127.0.0.1:9", token=TOKEN, name="offline-box", work_root=tmp_path / "work",
                        assets=str(tmp_path / "packs"), preload=["artist_test_tools"])
    runner = artist.Runner(cfg)
    assert _wait(lambda: runner.need_register.is_set(), 20)
    assert runner.packs["ok"] is False
    assert runner.packs["problems"]["fetch"] == ["OSError: network is unreachable"]
    assert runner.packs["problems"]["makehuman"] == ["missing rigs/default_weights.mhw"]
