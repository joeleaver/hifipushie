"""Local runner setup (artist_setup), self-update (artist_update) and the installer's --check
(scripts/install-runner.sh), against the fake department of test_artist.

Run: uv run pytest tests/test_artist_setup.py      (the real git-install test: -m slow is included by default)
"""

from __future__ import annotations

import io
import json
import os
import shutil
import stat
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import pytest

import test_artist as T  # (sets HIFIPUSHIE_HOME / XDG_* to temp dirs)
from hifipushie import artist, artist_setup as S, artist_update as U

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def dept():
    d = T.FakeDepartment()
    yield d
    d.server.shutdown()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A runner dir in a temp project, temp XDG dirs, systemctl recorded (never the real one)."""
    for k in ("XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        monkeypatch.setenv(k, str(tmp_path / k.lower()))
    monkeypatch.delenv("OXIDEGEN_RUNNER_DIR", raising=False)
    monkeypatch.delenv("OXIDEGEN_RUNNER_TOKEN", raising=False)
    calls = []

    def systemctl(*args, check=False):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(S, "systemctl", systemctl)
    monkeypatch.setattr(S, "has_systemd", lambda: True)
    monkeypatch.setattr(artist, "RUNNER_DIR", None)
    project = tmp_path / "project"
    project.mkdir()
    return project, project / ".oxidegen" / "runner", calls


def _mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


# ------------------------------------------------------------------------------------------- pairing

def test_pairing_approved_writes_a_private_token_that_works(dept, home, capsys):
    project, d, _ = home
    assert S.main(["login", "--url", dept.url, "--dir", str(d), "--no-browser", "--name", "box1"]) == 0
    out = capsys.readouterr().out
    assert "WDJB-MJHT" in out and dept.url + "/pair/WDJB-MJHT" in out and "Connected as box1" in out
    assert T.TOKEN not in out  # never printed
    tok = d / "token"
    assert tok.read_text().strip() == T.TOKEN and _mode(tok) == 0o600 and _mode(d) == 0o700
    assert json.loads((d / "runner.json").read_text())["url"] == dept.url
    assert S.token_works(dept.url, T.TOKEN) and not S.token_works(dept.url, "nope")
    # and a runner registers with it
    r = artist.Department(dept.url, tok.read_text().strip()).request(
        "POST", "/v1/runners/register", {"name": "box1", "artist": "sculpt", "capabilities": []})
    assert r["runner_id"]


@pytest.mark.parametrize("how", ["deny", "expire"])
def test_pairing_denied_or_expired_leaves_no_token(dept, home, how, capsys):
    project, d, _ = home
    dept.pairing = how
    assert S.main(["login", "--url", dept.url, "--dir", str(d), "--no-browser"]) == 1
    assert ("denied" if how == "deny" else "expired") in capsys.readouterr().out
    assert not (d / "token").exists()


def test_pairing_times_out(dept, home):
    dept.pairing = "pending"
    with pytest.raises(S.PairingFailed, match="expired"):
        S.pair(dept.url, "box", open_browser=False)


def test_logout_removes_the_token_and_stops_the_service(dept, home, capsys):
    project, d, calls = home
    S.write_private(d / "token", "t\n")
    S.install_service(d)
    assert S.main(["logout", "--dir", str(d)]) == 0
    assert not (d / "token").exists()
    assert ("disable", "--now", S.UNIT) in calls


# ------------------------------------------------------------------------------------------- setup

def _fake_blender(path: Path, version: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/bin/sh\necho 'Blender {version}'\n")
    path.chmod(0o755)
    return path


def _packs_tarball() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = b"model data"
        ti = tarfile.TarInfo("gnm/LICENSE")
        ti.size = len(data)
        t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def test_setup_with_a_code(dept, home, monkeypatch, tmp_path, capsys):
    project, d, calls = home
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    dept.codes["ABC-123"] = T.TOKEN
    packs = _packs_tarball()
    dept.files["packs.tgz"] = packs
    dept.install = {"git": {"repo": "https://example.invalid/hifipushie", "sha": "a" * 40},
                    "packs_url": "/files/packs.tgz", "packs_sha256": S.hashlib.sha256(packs).hexdigest(),
                    "blender": {"version": "5.1.2", "linux_x64_url": dept.url + "/files/none", "sha256": "0" * 64}}
    blender = _fake_blender(tmp_path / "bin" / "blender", "5.1.2")
    monkeypatch.setenv("HIFIPUSHIE_BLENDER", str(blender))
    monkeypatch.setattr(artist, "gpu_probe", lambda timeout=300.0, blender=None: {"workbench": "ok", "eevee": "ok"})

    def start(dd, use_systemd):  # the service "registers" (what the real runner writes)
        assert use_systemd
        artist.write_status({"state": "registered", "name": "box1", "at": time.time()})
        return "systemd user service (mocked)"

    monkeypatch.setattr(S, "start_service", start)
    assert S.main(["setup", "--url", dept.url, "--code", "ABC-123", "--dir", str(d), "--name", "box1",
                   "--no-browser"]) == 0
    out = capsys.readouterr().out
    assert "Connected: box1 is ready for sculpting" in out and T.TOKEN not in out
    assert (d / "token").read_text().strip() == T.TOKEN and _mode(d / "token") == 0o600
    cfg = json.loads((d / "runner.json").read_text())
    assert cfg["url"] == dept.url and cfg["name"] == "box1" and cfg["artist"] == "sculpt"
    assert cfg["blender"] == str(blender.resolve()) and "already installed" in out
    assert cfg["git_repo"] == "https://example.invalid/hifipushie"
    packs_dir = Path(cfg["assets"])
    assert (packs_dir / "gnm" / "LICENSE").read_bytes() == b"model data" and packs_dir.parent == S.cache_dir()
    env = (d / "runner.env").read_text()
    assert f"HIFIPUSHIE_BLENDER='{blender.resolve()}'" in env and str(packs_dir) in env and T.TOKEN not in env
    unit = S.unit_path().read_text()
    assert T.TOKEN not in unit and "RestartPreventExitStatus=77" in unit and f"X-OxidegenRunnerDir={d}" in unit
    assert f"ExecStart={S.launcher_path()} {d}" in unit and os.access(S.launcher_path(), os.X_OK)
    assert ("enable", S.UNIT) in calls
    assert ".oxidegen/" in (project / ".git" / "info" / "exclude").read_text()
    assert json.loads((d / "probe.json").read_text())["eevee"] == "ok"
    # a used code is gone; setup again reuses the working token (no code needed) and doesn't re-add the exclude
    assert S.main(["setup", "--url", dept.url, "--dir", str(d), "--no-browser"]) == 0
    assert (project / ".git" / "info" / "exclude").read_text().count(".oxidegen/") == 1
    assert dept.polls == 0  # no pairing: the saved token works


def test_setup_from_another_project_reuses_the_service_unless_moved(dept, home, monkeypatch, tmp_path, capsys):
    project, d, calls = home
    S.install_service(d)
    other = tmp_path / "other" / ".oxidegen" / "runner"
    assert S.main(["setup", "--url", dept.url, "--dir", str(other), "--no-browser"]) == 0
    assert "already set up for" in capsys.readouterr().out and S.installed_dir() == d
    assert S.main(["install", "--dir", str(other), "--move-here"]) == 0
    assert S.installed_dir() == other


def test_install_uninstall_and_status(home, capsys):
    project, d, calls = home
    assert S.main(["install", "--dir", str(d)]) == 0
    assert S.unit_path().exists() and ("daemon-reload",) in calls and ("enable", S.UNIT) in calls
    assert S.main(["status", "--dir", str(d)]) == 0
    st = json.loads(capsys.readouterr().out.split("\n", 1)[1])
    assert st["service"]["points_at"] == str(d) and st["token"] is False
    assert S.main(["uninstall"]) == 0
    assert not S.unit_path().exists() and ("disable", "--now", S.UNIT) in calls


def test_blender_detection_and_download(dept, home, monkeypatch, tmp_path):
    cache = tmp_path / "cache"
    monkeypatch.delenv("HIFIPUSHIE_BLENDER", raising=False)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")  # (no blender there; tar and xz are)
    old = _fake_blender(tmp_path / "old" / "blender", "4.2.0")
    monkeypatch.setenv("HIFIPUSHIE_BLENDER", str(old))  # the wrong series: not used
    with pytest.raises(RuntimeError, match="didn't say where"):
        S.ensure_blender({"blender": {"version": "5.1.2"}}, cache)
    # the portable build: a tar.xz with a blender at its top dir
    src = tmp_path / "src" / "blender-5.1.2-linux-x64"
    _fake_blender(src / "blender", "5.1.2")
    subprocess.run(["tar", "-cJf", str(tmp_path / "b.tar.xz"), "-C", str(src.parent), src.name], check=True)
    data = (tmp_path / "b.tar.xz").read_bytes()
    dept.files["b.tar.xz"] = data
    info = {"blender": {"version": "5.1.2", "linux_x64_url": dept.url + "/files/b.tar.xz",
                        "sha256": S.hashlib.sha256(data).hexdigest()}}
    bad = {"blender": {**info["blender"], "sha256": "0" * 64}}
    with pytest.raises(RuntimeError, match="sha256"):
        S.ensure_blender(bad, cache)
    exe, note = S.ensure_blender(info, cache)
    assert exe == str(cache / "blender-5.1.2" / "blender") and "downloaded" in note
    assert S.ensure_blender(info, cache)[1].endswith("(shared cache)")
    with pytest.raises(RuntimeError, match="sha256"):  # packs are checked too
        S.ensure_packs({"packs_url": dept.url + "/files/b.tar.xz", "packs_sha256": "1" * 64, "_base": dept.url}, cache)


# ------------------------------------------------------------------------------------------- self-update

def _layout(cache: Path, current: str):
    (cache / "tools" / current / "bin").mkdir(parents=True, exist_ok=True)
    os.symlink(f"tools/{current}", cache / "sculpt-current")


def test_update_failed_check_is_remembered_and_reported(dept, tmp_path, monkeypatch):
    cache, d = tmp_path / "cache", tmp_path / "runner"
    _layout(cache, "1" * 40)
    u = U.Updater(cache, d, "1" * 40)

    def fake_install(c, repo, sha, timeout=0):
        exe = c / "tools" / sha / "bin" / "hifipushie-artist"
        exe.parent.mkdir(parents=True)
        exe.write_text("")
        return exe

    monkeypatch.setattr(U, "install", fake_install)
    monkeypatch.setattr(U, "check", lambda exe, timeout=0: "probe failed: boom")
    want = ("2" * 40, "")
    assert u.due(want)
    assert "boom" in u.update(want)
    assert os.readlink(cache / "sculpt-current") == "tools/" + "1" * 40  # not switched
    assert not (cache / "tools" / ("2" * 40)).exists() and u.last_failed() == "2" * 40
    u.last_try = 0
    assert not u.due(want)  # a failed sha is never retried
    # ... and the runner reports it in heartbeats
    cfg = artist.Config(url=dept.url, token=T.TOKEN, name="upd", work_root=tmp_path / "w", updater=u)
    runner = artist.Runner(cfg)
    t = threading.Thread(target=runner.run, daemon=True)
    t.start()
    try:
        deadline = time.time() + 20
        while not any(h.get("update_failed") == "2" * 40 for h in dept.heartbeats) and time.time() < deadline:
            time.sleep(0.05)
        assert any(h.get("update_failed") == "2" * 40 for h in dept.heartbeats)
        assert dept.registrations[-1]["update_failed"] == "2" * 40
    finally:
        runner.stop.set()
        t.join(10)


def test_no_update_mid_session_then_switch_when_idle(dept, tmp_path, monkeypatch):
    cache, d = tmp_path / "cache", tmp_path / "runner"
    old, new = "1" * 40, "3" * 40
    _layout(cache, old)
    u = U.Updater(cache, d, old)
    switched = threading.Event()

    def fake_update(want):
        assert runner.session is None and runner.task_id is None
        U._write_json(d / "update-pending", {"from": old, "to": want[0], "at": time.time()})
        U._symlink(f"tools/{want[0]}", cache / "sculpt-current")
        U._symlink(f"tools/{old}", cache / "sculpt-previous")
        return None

    monkeypatch.setattr(u, "update", fake_update)
    monkeypatch.setattr(u, "reexec", lambda: (switched.set(), runner.stop.set()))
    cfg = artist.Config(url=dept.url, token=T.TOKEN, name="upd2", work_root=tmp_path / "w",
                        preload=["artist_test_tools"], updater=u)
    runner = artist.Runner(cfg)
    dept.wanted_version = new
    sid = "s-upd"
    # a session is open before the runner even polls: no update while it lasts
    dept.submit(sid, "_open", {"subject": {"kind": "model", "name": "m", "version": None}, "workspace": sid})
    tid = dept.submit(sid, "nap", {"secs": 1.5})
    t = threading.Thread(target=runner.run, daemon=True)
    t.start()
    try:
        assert dept.wait(tid, 60)["status"] == "ok"
        time.sleep(1.0)  # idle polls with a session open
        assert not switched.is_set()
        assert dept.run(sid, "_close")["status"] == "ok"
        assert switched.wait(20)
        assert os.readlink(cache / "sculpt-current") == f"tools/{new}"
    finally:
        runner.stop.set()
        t.join(10)
    # the new version confirms on registering; a version that never registers rolls back
    u2 = U.Updater(cache, d, new)
    assert u2.pending()["to"] == new and not u2.overdue(registered=True)
    u2.started = time.time() - 120
    U._write_json(d / "update-pending", {"from": old, "to": new, "at": time.time() - 120})
    assert u2.overdue(registered=False)
    u2.rollback("never registered")
    assert os.readlink(cache / "sculpt-current") == f"tools/{old}" and u2.last_failed() == new
    U._write_json(d / "update-pending", {"from": old, "to": new, "at": time.time()})
    u2.confirm()
    assert u2.pending() is None


@pytest.mark.skipif(not shutil.which("uv") or not shutil.which("git"), reason="needs uv and git")
def test_real_git_install_and_check(tmp_path, monkeypatch):
    """The git path for real: uv tool install git+file://<this repo>@HEAD into a side-by-side env, then the
    sanity check (--capabilities, the Blender probe)."""
    sha = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    cache = tmp_path / "cache"
    orig = U.uv_env  # (this machine's uv cache: no re-downloading every dependency)
    monkeypatch.setattr(U, "uv_env", lambda c, s: {k: v for k, v in orig(c, s).items()
                                                   if k not in ("UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR")})
    exe = U.install(cache, f"file://{REPO}", sha)
    assert exe == cache / "tools" / sha / "bin" / "hifipushie-artist"
    r = subprocess.run([str(exe), "--capabilities"], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and '"snapshot"' in r.stdout
    prefix = subprocess.run([str(exe.parent.parent / "hifipushie" / "bin" / "python"), "-c",
                             "from hifipushie.artist_update import running_sha; print(running_sha())"],
                            capture_output=True, text=True).stdout.strip()
    assert prefix == sha  # the version string carries the git sha (direct_url.json)
    if shutil.which("blender"):
        assert U.check(exe) is None


# ------------------------------------------------------------------------------------------- installer --check

SCRIPT = REPO / "scripts" / "install-runner.sh"


def _fakebin(tmp_path: Path, **tools: str) -> Path:
    b = tmp_path / "fakebin"
    b.mkdir(exist_ok=True)
    for name, body in tools.items():
        (b / name).write_text("#!/bin/sh\n" + body + "\n")
        (b / name).chmod(0o755)
    return b


LIBS = ["libGL.so.1", "libEGL.so.1", "libX11.so.6", "libXext.so.6", "libXi.so.6", "libXfixes.so.3",
        "libXrender.so.1", "libXxf86vm.so.1", "libxkbcommon.so.0", "libSM.so.6", "libICE.so.6"]


def _check(tmp_path, libs=LIBS, systemd="running", df_kb=50_000_000, extra=None):
    ld = "\n".join(f"\t{l} (libc6,x86-64) => /usr/lib/x86_64-linux-gnu/{l}" for l in libs)
    tools = {"ldconfig": f"cat <<'EOF'\n{len(libs)} libs found\n{ld}\nEOF",
             "systemctl": f"echo {systemd}",
             "df": f"echo 'Filesystem 1024-blocks Used Available Capacity Mounted'; echo \"/dev/fake 100 0 {df_kb} 1% /\"",
             "nvidia-smi": "exit 1", "rocminfo": "exit 1", "blender": "exit 1"}
    tools.update(extra or {})
    b = _fakebin(tmp_path, **tools)
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": f"{b}:/usr/bin:/bin", "HOME": str(home)}
    r = subprocess.run(["sh", str(SCRIPT), "--check", "--project", str(tmp_path)], capture_output=True, text=True,
                       env=env, timeout=120)
    return r.returncode, json.loads(r.stdout), r.stderr


def test_check_good_fit_or_limits(tmp_path):
    code, rep, err = _check(tmp_path)
    assert rep["missing_libs"] == "" and rep["systemd_user"] is True and rep["department"] == "skipped"
    # (this machine's RAM/GPU decide 0 vs 3; never a non-fit with everything present)
    assert code in (0, 3) and rep["fit"] == code and "Fit:" in err


def test_check_without_systemd_works_with_limits(tmp_path):
    code, rep, err = _check(tmp_path, systemd="offline")
    assert rep["systemd_user"] is False and code in (3,) and "background process" in rep["notes"]


def test_check_low_disk_is_not_a_fit(tmp_path):
    code, rep, err = _check(tmp_path, df_kb=1_000_000)  # ~1 GB free
    assert code == 4 and rep["disk_free_mb"]["cache"] == 976 and "disk:" in rep["notes"]


def test_check_missing_libs_names_the_install_command(tmp_path):
    code, rep, err = _check(tmp_path, libs=[l for l in LIBS if l not in ("libXi.so.6", "libEGL.so.1")],
                            extra={"apt-get": "exit 0", "dnf": "exit 1"})
    assert code == 4
    assert set(rep["missing_libs"].split()) == {"libXi.so.6", "libEGL.so.1"}
    assert rep["install_command"] == "sudo apt-get install -y libegl1 libxi6"


def test_check_unsupported_os(tmp_path):
    code, rep, err = _check(tmp_path, extra={"uname": 'case "$1" in -s) echo Darwin ;; -m) echo arm64 ;; esac'})
    assert code == 4 and "isn't supported yet" in rep["notes"]


def test_installer_script_is_clean_sh():
    if shutil.which("shellcheck"):
        r = subprocess.run(["shellcheck", "-s", "sh", str(SCRIPT)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout
    r = subprocess.run(["sh", "-n", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
