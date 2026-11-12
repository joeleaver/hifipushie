"""A model's live Blender scene (workspace/<model>/scene.blend): the spec stays the source of truth, the scene is
derived from it, and what a person changes in it comes back as spec edits.

Objects: every part (minus the instances of shared prefabs) and every shared prefab's parts are meshed on their
own and cached by content (a hash of their primitives and voxel), so an edit re-meshes only what it touched.
Scene parts are meshed at the scene voxel on a lattice fixed in space (unrelated edits don't move it); a prefab's
parts in its own frame, at up to `resolution` voxels across the prefab. Instances are collection instances.

Round trip: `pull` reads the saved .blend and turns moved, turned or scaled instances into instance edits (the
weather's offsets taken back out, so the spec + weather lands where the person put it). `sync` pulls first, so
nothing a person did is overwritten, then writes the spec's state.

Where the code is (split by responsibility, as C424): this module is the family's base and holds EVERY constant (set
and read at scene.NAME: C422). scene_inputs: inputs to the scene's materials: calibration, world and placed points,
the raytraced inputs, paint inputs. scene_objects: the scene's objects: part voxels, refine boxes, the face's refine
and gap, the live grid, `objects`, the cache's pruning. scene_sync: `sync` and `pull`: what comes back from Blender
(parameters, decals, painted masks), clashes, part hashes, `look`.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from . import render, sdf, store
from . import moved

SCRIPT = Path(__file__).with_name("blender_scene.py")


def blend_path(name: str) -> Path:
    return store._dir(name) / "scene.blend"


LIVE_PORT = int(__import__("os").environ.get("BLENDER_MCP_PORT", "9876"))


def _live_call(code: str, timeout: float = 600.0, port: int | None = None) -> dict | None:
    """Run Python in a person's running Blender over the Blender MCP add-on's socket (JSON + NUL). None when
    no Blender is listening, or when HIFIPUSHIE_NO_LIVE is set (an oxidegen artist runner: specs are data, and no
    tool may reach a Blender session on the host)."""
    import os
    import socket
    if os.environ.get("HIFIPUSHIE_NO_LIVE"):
        return None
    try:
        with socket.create_connection(("localhost", port or LIVE_PORT), timeout=1.0) as sock:
            sock.settimeout(timeout)
            sock.sendall(json.dumps({"type": "execute", "code": code, "strict_json": False}).encode() + b"\0")
            buf = bytearray()
            while b"\0" not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
    except OSError:
        return None
    if not buf:
        return None
    return json.loads(bytes(buf).partition(b"\0")[0].decode())


def live_session(name: str) -> bool:
    """Is the model's scene.blend open in a person's running Blender (the Blender MCP add-on listening)? Then
    syncs and pulls happen in that session, so edits show as they're made and theirs come back unsaved."""
    r = _live_call("import bpy\nresult = {'file': bpy.data.filepath}", timeout=5.0)
    if not r or r.get("status") != "ok":
        return False
    f = (r.get("result") or {}).get("file") or ""
    return bool(f) and Path(f).resolve() == blend_path(name).resolve()


def _blender_live(job: dict) -> str:
    """blender_scene's job, run inside the live session (it imports the module; nothing is opened or reloaded
    from disk, and a sync saves the session to scene.blend so headless renders see it)."""
    code = ("import sys, importlib, json\n"
            f"sys.path.insert(0, {str(SCRIPT.parent)!r})\n"
            "import blender_hair, blender_scene as B\n"
            "importlib.reload(blender_hair)\n"  # (reloading B alone kept a stale blender_hair in a long session)
            "importlib.reload(B)\n"
            f"B.MODES[{job['mode']!r}](json.loads({json.dumps({**job, 'live': True})!r}))\n"
            "result = {}")
    r = _live_call(code, timeout=3600.0)
    if r is None:
        raise RuntimeError("the live Blender session went away")
    if r.get("status") != "ok":
        raise RuntimeError(f"live Blender failed: {r.get('message')}\n{r.get('stderr', '')[-2000:]}")
    return str(r.get("stdout") or "")


def _blender(job: dict, timeout: float = 900, progress=None) -> str:
    """Run blender_scene.py on a job. progress(line) gets each "@@progress" line as Blender prints it."""
    with tempfile.TemporaryDirectory(prefix="hifipushie-scene-") as tmp:
        p = Path(tmp) / "job.json"
        p.write_text(json.dumps(job))
        cmd = [render.BLENDER, "-b", *render._threads(), "--factory-startup", "--python-exit-code", "1", "--python", str(SCRIPT), "--", str(p)]
        if progress is None:
            from . import resources  # killed with a heavy job whose tool call is cancelled
            r = resources.run(cmd, capture_output=True, text=True, timeout=timeout)
            out, err, code = r.stdout, r.stderr, r.returncode
        else:
            import threading
            from . import resources
            proc = resources.track(subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
            errs = []
            t = threading.Thread(target=lambda: errs.append(proc.stderr.read()), daemon=True)
            t.start()
            lines = []
            timer = threading.Timer(timeout, proc.kill)
            timer.start()
            try:
                for line in proc.stdout:
                    lines.append(line)
                    if line.startswith("@@progress"):
                        progress(line[11:].rstrip())
                code = proc.wait()
            finally:
                timer.cancel()
            t.join(5)
            out, err = "".join(lines), "".join(errs)
        if code:
            raise RuntimeError(f"blender failed:\n{out[-3000:]}\n{err[-3000:]}")
        if "out of SVM stack space" in out or "out of SVM stack space" in err:
            # Cycles gives up on a material too big for its 255-slot shader stack and renders or bakes it BLACK
            # without failing: say so instead of handing back black maps
            import re
            which = sorted(set(re.findall(r'shader "([^"]+)" too big', out + err)))
            raise RuntimeError(
                f"Cycles ran out of shader stack on material(s) {which or '?'}: it would render or bake them black. A part's "
                f"material holds a few dozen paint layers in Cycles (each layer's exposed numbers and every layer with "
                f"\"height\" cost stack; the Bump node compiles the height layers three times). Thin the part's layers "
                f"(fewer layers with height, merge masks, measure broad masks per vertex with \"vertex\": true, or for "
                f"skin fewer scars / tattoos / make-up items), or look with EEVEE.")
        return out


def _hash(ps: list, frame, extra: str = "") -> str:
    h = hashlib.sha1(extra.encode())
    for p in ps:
        h.update(sdf.fingerprint(p).encode())
        if p.kind == "shell":  # a shell follows its base part
            for q in p.params["prims"]:
                h.update(sdf.fingerprint(q).encode())
    lo, vx, shape = frame
    h.update(np.round(np.asarray(lo), 6).tobytes() + np.float64(vx).tobytes() + np.asarray(shape, np.int64).tobytes())
    return h.hexdigest()[:16]


FACE_REFINE_VOXEL = 0.001  # (r68) m: the scene part carrying a kept approved face is meshed this fine over it
FACE_REFINE_PAD = 0.012  # m round the kept face's clusters (the keep fades over 3 rings of quads past its groups)
FACE_GAP_MAX_MM = 0.2  # median kept-face -> scene-mesh distance above this: the bake's source is off the export

# Per model, per scene part: its block grid and projected mesh from the last sync (like store._LIVE), so an edit
# to a big part (a window cut into the logs) re-meshes only the blocks the change can reach. Grids of fine-voxel
# parts are big: a model keeps at most LIVE_CELLS of them (the most recently used), the rest mesh cold.
_LIVE: dict[str, dict] = {}
LIVE_CELLS = 750_000_000  # ~3 GB of float32 per model

KEEP_SYNCS = 3  # the scene cache keeps what the last few syncs used (a quick undo stays cheap) and no more

LAYOUT = 2  # what an object's packed inputs file holds (2: ao_raw for the export's AO map): bump on change
VECTOR_INPUTS = ("grain", "radial")  # per-vertex vectors: an attribute each, not packed
RAYTRACED = ("ao", "sky")  # inputs Cycles measures (the rest are ours: curvature is exact from the field)
# AO as ours (cones out to 3 steps of 0.008 x the model size). Sky reaches past the whole model: a roof shelters
# however high it is (ours stopped at 0.3 x, so interior walls read as open to the sky). x model size.
RT = {"ao_distance": 0.024, "sky_distance": 2.0, "samples": 32, "smooth": 2}
CALIBRATION = json.loads(Path(__file__).with_name("input_quantiles.json").read_text()) \
    if Path(__file__).with_name("input_quantiles.json").exists() else {}


# The modules this one was split into (as C424). Its constants stay HERE (C422): tests/test_constants_address.py.
MODULES = ("scene_inputs", "scene_objects", "scene_sync")
__getattr__ = moved.refuse(__name__, MODULES)  # a name that moved says where it is now (C426)
