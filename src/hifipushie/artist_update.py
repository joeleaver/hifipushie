"""Runner self-update: the department pins a hifipushie git sha (`wanted_version` in register/heartbeat replies);
runners follow it.

LOCAL (installed by scripts/install-runner.sh + `setup`): every version is its own uv tool env under the shared
cache, `<cache>/tools/<sha>/` (bin/hifipushie-artist), with two symlinks: `sculpt-current` (what the service runs,
through the launcher) and `sculpt-previous`. When the runner is idle (no session, no task) and the wanted sha
differs, it installs the new sha alongside, checks it (`--capabilities`: import + capability derivation; `probe`:
Blender renders), switches the symlinks, writes `update-pending` in the runner dir and re-execs into the new
version. The new version confirms on its first successful registration; if it doesn't register within 60 s it
rolls back itself, and if it can't even start, the launcher rolls back (it checks `update-pending` before each
start). A failed sha is remembered (`update-failed.json`) and reported in heartbeats as `update_failed`; never retried.
At most one attempt per 10 min, never mid-session.

HOSTED (the image): at container start, if OXIDEGEN_WANTED_VERSION differs from the baked sha, a copy of the
image's venv gets that sha installed over it (deps are already there) and is run as a child; if that fails or
doesn't register within 60 s, the baked version runs instead and reports update_failed.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger("hifipushie.artist")

DEFAULT_REPO = "https://github.com/joeleaver/hifipushie"
CHECK_EVERY = 600.0  # seconds between update attempts
CONFIRM_SECS = 60.0  # a new version must register within this


def running_sha() -> str:
    """The git sha this hifipushie was installed from: uv/pip record it for a git install (direct_url.json); the
    hosted image bakes HIFIPUSHIE_GIT_SHA; a checkout asks git."""
    from importlib.metadata import PackageNotFoundError, distribution
    try:
        d = json.loads(distribution("hifipushie").read_text("direct_url.json") or "{}")
        sha = (d.get("vcs_info") or {}).get("commit_id")
        if sha:
            return sha
    except (PackageNotFoundError, ValueError, OSError):
        pass
    if os.environ.get("HIFIPUSHIE_GIT_SHA"):
        return os.environ["HIFIPUSHIE_GIT_SHA"]
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(__file__).parent, capture_output=True,
                              text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def wanted(reply: dict | None) -> tuple[str, str] | None:
    """(sha, repo) from a register/heartbeat reply's `wanted_version` (a sha, or {"sha", "repo"})."""
    w = (reply or {}).get("wanted_version")
    if isinstance(w, str) and w.strip():
        return w.strip(), ""
    if isinstance(w, dict) and w.get("sha"):
        return str(w["sha"]), str(w.get("repo") or "")
    return None


def same(a: str, b: str) -> bool:
    """Shas equal, allowing either to be abbreviated (>= 7 chars)."""
    a, b = a.lower(), b.lower()
    n = min(len(a), len(b))
    return n >= 7 and a[:n] == b[:n]


def uv_bin(cache: Path) -> str | None:
    p = cache / "bin" / "uv"
    return str(p) if p.exists() else shutil.which("uv")


def uv_env(cache: Path, sha: str) -> dict:
    tools = cache / "tools" / sha
    return {**os.environ, "UV_TOOL_DIR": str(tools), "UV_TOOL_BIN_DIR": str(tools / "bin"),
            "UV_CACHE_DIR": str(cache / "uv"), "UV_PYTHON_INSTALL_DIR": str(cache / "python")}


def install(cache: Path, repo: str, sha: str, timeout: float = 1800) -> Path:
    """`uv tool install` sha into its own env (<cache>/tools/<sha>); returns its hifipushie-artist."""
    uv = uv_bin(cache)
    if not uv:
        raise RuntimeError("no uv (expected in <cache>/bin or on PATH)")
    src = f"git+{repo}@{sha}"
    r = subprocess.run([uv, "tool", "install", "--force", "--python", "3.12", src], env=uv_env(cache, sha),
                       capture_output=True, text=True, timeout=timeout)
    exe = cache / "tools" / sha / "bin" / "hifipushie-artist"
    if r.returncode or not exe.exists():
        raise RuntimeError(f"uv tool install {src} failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    return exe


def check(exe: Path, timeout: float = 600) -> str | None:
    """None if the installed version works: it derives its capabilities and Blender renders (the probe)."""
    try:
        r = subprocess.run([str(exe), "--capabilities"], capture_output=True, text=True, timeout=timeout)
        if r.returncode or '"capabilities"' not in r.stdout:
            return f"--capabilities failed ({r.returncode}): {(r.stderr or r.stdout)[-500:]}"
        r = subprocess.run([str(exe), "probe"], capture_output=True, text=True, timeout=timeout)
        if r.returncode:
            return f"probe failed ({r.returncode}): {(r.stderr or r.stdout)[-500:]}"
        probe = json.loads(r.stdout.strip().splitlines()[-1])
        if probe.get("workbench") != "ok" and probe.get("eevee") != "ok":
            return f"Blender doesn't render with this version: {probe}"
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as e:
        return f"check failed: {e}"
    return None


class Updater:
    """A local runner's self-update (see the module doc). `cache` holds tools/<sha>, sculpt-current/-previous."""

    def __init__(self, cache: Path, runner_dir: Path, current: str, repo: str = DEFAULT_REPO,
                 artist: str = "sculpt"):
        self.cache, self.dir, self.current, self.repo = cache, runner_dir, current, repo or DEFAULT_REPO
        self.cur_link, self.prev_link = cache / f"{artist}-current", cache / f"{artist}-previous"
        self.last_try = 0.0
        self.check_every = CHECK_EVERY
        self.started = time.time()

    @classmethod
    def for_this_install(cls, runner_dir: Path | None, repo: str = "") -> "Updater | None":
        """An updater when this process runs from an installed tool env (<cache>/tools/<sha>/...), else None
        (a checkout, the hosted image, tests)."""
        if runner_dir is None:
            return None
        prefix = Path(sys.prefix).resolve()
        for parent in prefix.parents:
            if parent.name == "tools" and (parent.parent / "sculpt-current").is_symlink():
                sha = running_sha()
                return cls(parent.parent, runner_dir, sha, repo) if sha else None
        return None

    # -- bookkeeping in the runner dir
    def failed(self) -> dict:
        try:
            return json.loads((self.dir / "update-failed.json").read_text())
        except (OSError, ValueError):
            return {}

    def last_failed(self) -> str | None:
        f = self.failed()
        return max(f, key=lambda k: f[k].get("at", 0)) if f else None

    def _mark_failed(self, sha: str, why: str):
        f = self.failed()
        f[sha] = {"at": time.time(), "why": why[:1000]}
        _write_json(self.dir / "update-failed.json", f)
        log.error("update to %s failed: %s", sha[:12], why)

    def pending(self) -> dict | None:
        try:
            return json.loads((self.dir / "update-pending").read_text())
        except (OSError, ValueError):
            return None

    # -- the update
    def due(self, want: tuple[str, str] | None) -> bool:
        if not want or not self.current or same(want[0], self.current):
            return False
        if any(same(want[0], s) for s in self.failed()):
            return False
        return time.time() - self.last_try >= self.check_every

    def update(self, want: tuple[str, str]) -> str | None:
        """Install, check and switch to the wanted sha. None = switched (call reexec()); else why it failed."""
        sha, repo = want[0], want[1] or self.repo
        self.last_try = time.time()
        log.info("updating %s -> %s (%s)", self.current[:12], sha[:12], repo)
        try:
            exe = install(self.cache, repo, sha)
        except (RuntimeError, OSError, subprocess.SubprocessError) as e:
            self._mark_failed(sha, str(e))
            return str(e)
        why = check(exe)
        if why:
            self._mark_failed(sha, why)
            shutil.rmtree(self.cache / "tools" / sha, ignore_errors=True)
            return why
        old = os.readlink(self.cur_link) if self.cur_link.is_symlink() else None
        _write_json(self.dir / "update-pending", {"from": self.current, "to": sha, "at": time.time()})
        if old:
            _symlink(old, self.prev_link)
        _symlink(str(Path("tools") / sha), self.cur_link)
        log.info("switched to %s; restarting", sha[:12])
        return None

    def confirm(self):
        """After a successful registration: a pending update to this version is done."""
        p = self.pending()
        if p and same(p.get("to", ""), self.current):
            (self.dir / "update-pending").unlink(missing_ok=True)
            prev = p.get("from") or ""
            log.info("update to %s confirmed (previous %s kept)", self.current[:12], prev[:12])

    def overdue(self, registered: bool) -> bool:
        """This version was switched to and hasn't registered within CONFIRM_SECS."""
        p = self.pending()
        return bool(p and not registered and same(p.get("to", ""), self.current)
                    and time.time() - max(p.get("at", 0), self.started) > CONFIRM_SECS)

    def rollback(self, why: str):
        p = self.pending() or {}
        self._mark_failed(p.get("to") or self.current, why)
        if self.prev_link.is_symlink():
            _symlink(os.readlink(self.prev_link), self.cur_link)
        (self.dir / "update-pending").unlink(missing_ok=True)

    def reexec(self):  # (does not return)
        exe = self.cur_link / "bin" / "hifipushie-artist"
        os.execv(str(exe), [str(exe), "run", "--dir", str(self.dir)])


def _write_json(p: Path, d) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(d))
    tmp.replace(p)


def _symlink(target: str, link: Path) -> None:
    tmp = link.with_name(link.name + ".new")
    tmp.unlink(missing_ok=True)
    os.symlink(target, tmp)
    tmp.replace(link)


# ---------------------------------------------------------------------------------------------- hosted

def hosted_update(want: str, repo: str, root: Path, timeout: float = 1800) -> tuple[Path | None, str | None]:
    """A copy of the image's venv with `want` installed over it: (python, None) or (None, why)."""
    uv = shutil.which("uv")
    if not uv:
        return None, "no uv in the image"
    venv = root / f".runner-{want[:12]}"
    try:
        shutil.rmtree(venv, ignore_errors=True)
        shutil.copytree(sys.prefix, venv, symlinks=True)
        r = subprocess.run([uv, "pip", "install", "--python", str(venv / "bin" / "python"), f"git+{repo}@{want}"],
                           capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, "UV_CACHE_DIR": str(root / ".uv-cache")})
        if r.returncode:
            return None, f"uv pip install failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}"
        py = venv / "bin" / "python"
        r = subprocess.run([str(py), "-m", "hifipushie.artist", "--capabilities"], capture_output=True, text=True,
                           timeout=600)
        if r.returncode or '"capabilities"' not in r.stdout:
            return None, f"--capabilities failed ({r.returncode}): {(r.stderr or r.stdout)[-500:]}"
        return py, None
    except (OSError, subprocess.SubprocessError, shutil.Error) as e:
        return None, f"{type(e).__name__}: {e}"
