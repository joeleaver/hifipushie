"""Setting up a LOCAL sculpt runner: `hifipushie-artist setup | login | logout | install | uninstall | status`.

Normally run by scripts/install-runner.sh (which the department serves as /install/runner.sh): it checks the
machine, installs uv and this code (`uv tool install git+...@<sha>` into the shared cache), then runs
`hifipushie-artist setup --url <dept> --code <one-time code>`. Layout:

  <project>/.oxidegen/runner/        this project's runner: runner.json (url, name, artist, ...), token (0600),
                                     runner.env (the launcher's environment), status.json, logs/, work/ (sessions)
  ${XDG_CACHE_HOME:-~/.cache}/oxidegen/   shared by every project: bin/uv, bin/oxidegen-runner-sculpt (the launcher),
                                     tools/<sha>/ (uv tool envs), sculpt-current|-previous, blender-<ver>/,
                                     packs-<sha>/, uv/ (uv's cache), python/
  ~/.config/systemd/user/oxidegen-runner-sculpt.service   one per user, pointing at one runner dir

The token never goes into the unit file, the env file or the logs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import artist
from .artist import DEFAULT_URL, DISCONNECTED, EXIT_UNAUTHORIZED, Department, HTTPError

ARTIST = "sculpt"
UNIT = f"oxidegen-runner-{ARTIST}.service"
NIL_RUNNER = "00000000-0000-0000-0000-000000000000"
WAIT_ONLINE = 90.0


def say(msg: str = ""):
    print(msg, flush=True)


# ---------------------------------------------------------------------------------------------- places

def cache_dir() -> Path:
    return Path(os.environ.get("XDG_CACHE_HOME") or "~/.cache").expanduser() / "oxidegen"


def unit_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or "~/.config").expanduser() / "systemd" / "user" / UNIT


def launcher_path() -> Path:
    return cache_dir() / "bin" / f"oxidegen-runner-{ARTIST}"


def default_dir() -> Path:
    return Path.cwd() / ".oxidegen" / "runner"


def supported() -> str | None:
    """None on Linux x86_64; else why not."""
    if platform.system() != "Linux":
        return f"{platform.system()} isn't supported yet (Linux x86_64 only for now)"
    if platform.machine() not in ("x86_64", "AMD64"):
        return f"{platform.machine()} isn't supported yet (Linux x86_64 only for now)"
    return None


# ---------------------------------------------------------------------------------------------- token and config

def write_private(path: Path, text: str) -> None:
    """Atomically, 0600, in a 0700 directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, text.encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def read_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(d: Path, **kv) -> dict:
    cfg = read_json(d / "runner.json")
    cfg.update({k: v for k, v in kv.items() if v is not None})
    cfg.setdefault("artist", ARTIST)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / "runner.json.tmp"
    tmp.write_text(json.dumps(cfg, indent=1) + "\n")
    tmp.replace(d / "runner.json")
    return cfg


def token_works(url: str, token: str) -> bool:
    """Does the department accept this token? A heartbeat for a runner that doesn't exist: 401/403 = refused, any
    other answer (404) = accepted. No side effects (registering would end a running runner's session)."""
    try:
        Department(url, token).request("POST", f"/v1/runners/{NIL_RUNNER}/heartbeat", {"task": None, "message": None})
    except HTTPError as e:
        return e.status not in (401, 403)
    return True


def redeem(url: str, code: str, name: str) -> str:
    r = Department(url, "").request("POST", "/v1/runner-pairings/redeem",
                                     {"code": code, "artist": ARTIST, "name": name, "hostname": socket.gethostname()})
    tok = (r or {}).get("token")
    if not tok:
        raise RuntimeError("the department answered the code without a token")
    return tok


class PairingFailed(Exception):
    pass


def pair(url: str, name: str, open_browser: bool = True, sleep=time.sleep) -> str:
    """The browser flow (like `gh auth login`): show a code, the person approves it in oxidegen, we get a token."""
    dept = Department(url, "")
    r = dept.request("POST", "/v1/runner-pairings", {"artist": ARTIST, "name": name, "hostname": socket.gethostname()})
    say(f"To connect this computer, open {r['verify_url']} and check the code is {r['user_code']}")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(r["verify_url"])
        except Exception:  # (no browser is fine: the link is printed)
            pass
    deadline = time.time() + float(r.get("expires_in") or 600)
    every = float(r.get("poll_secs") or 3)
    while time.time() < deadline:
        sleep(every)
        try:
            p = dept.request("POST", "/v1/runner-pairings/poll",
                             {"pairing_id": r["pairing_id"], "device_secret": r["device_secret"]})
        except HTTPError as e:
            if e.status == 410:
                status = (_json(e.body) or {}).get("status") or "expired"
                raise PairingFailed(f"the pairing was {status}") from None
            raise
        if (p or {}).get("status") == "approved" and p.get("token"):
            return p["token"]
    raise PairingFailed("the pairing expired")


def _json(text: str):
    try:
        return json.loads(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------------------------- downloads

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, sha256: str, label: str) -> Path:
    """To dest, sha256-checked; a .part left by an interrupted download is resumed (HTTP Range)."""
    if dest.exists() and sha256_file(dest) == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    # download.blender.org answers 403 to urllib's default agent
    req = urllib.request.Request(url, headers={"User-Agent": "hifipushie-setup/1 (+python-urllib)"})
    if have:
        req.add_header("Range", f"bytes={have}-")
    with urllib.request.urlopen(req, timeout=60) as r:
        mode = "ab" if have and r.status == 206 else "wb"
        total = int(r.headers.get("Content-Length") or 0) + (have if mode == "ab" else 0)
        done, last = (have if mode == "ab" else 0), 0.0
        with open(part, mode) as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
                done += len(chunk)
                if time.time() - last > 5:
                    last = time.time()
                    say(f"  {label}: {done / 1e6:.0f}" + (f" / {total / 1e6:.0f} MB" if total else " MB"))
    got = sha256_file(part)
    if got != sha256:
        part.unlink()
        raise RuntimeError(f"{label}: sha256 {got} != {sha256} (download removed)")
    part.replace(dest)
    return dest


def blender_version(exe: str) -> str | None:
    try:
        r = subprocess.run([exe, "--background", "--factory-startup", "--version"], capture_output=True, text=True,
                           timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"Blender (\d+\.\d+\.\d+)", r.stdout)
    return m.group(1) if m else None


def ensure_blender(info: dict, cache: Path) -> tuple[str, str]:
    """(blender executable, how it was found): $HIFIPUSHIE_BLENDER or PATH when it's the wanted major.minor, else
    the portable build in the cache (downloaded, sha256-checked)."""
    b = info.get("blender") or {}
    want = b.get("version") or "5.1.2"
    series = ".".join(want.split(".")[:2])
    for cand in filter(None, (os.environ.get("HIFIPUSHIE_BLENDER"), shutil.which("blender"))):
        v = blender_version(cand)
        if v and ".".join(v.split(".")[:2]) == series:
            return str(Path(cand).resolve()), f"Blender {v} already installed ({cand})"
    home = cache / f"blender-{want}"
    exe = home / "blender"
    if exe.exists() and blender_version(str(exe)):
        return str(exe), f"Blender {want} (shared cache)"
    if not b.get("linux_x64_url") or not b.get("sha256"):
        raise RuntimeError(f"no Blender {series} here and the department didn't say where to get it")
    say(f"Downloading Blender {want} ...")
    tar = download(b["linux_x64_url"], cache / f"blender-{want}.tar.xz", b["sha256"], f"Blender {want}")
    tmp = cache / f"blender-{want}.unpack"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    subprocess.run(["tar", "-xJf", str(tar), "-C", str(tmp), "--strip-components=1"], check=True)
    shutil.rmtree(home, ignore_errors=True)
    tmp.replace(home)
    tar.unlink()
    if not blender_version(str(exe)):
        raise RuntimeError(f"the downloaded Blender doesn't run ({exe} --version)")
    return str(exe), f"Blender {want} downloaded to {home}"


def ensure_packs(info: dict, cache: Path) -> tuple[str | None, str]:
    """(the packs directory for HIFIPUSHIE_ASSETS, note): the department's tarball, sha256-checked, extracted
    once into the shared cache (packs-<sha12>/)."""
    url, sha = info.get("packs_url"), info.get("packs_sha256")
    if not url or not sha:
        return None, "no asset packs offered by the department (GNM/MakeHuman bases will fail)"
    url = url if url.startswith(("http://", "https://")) else info["_base"].rstrip("/") + url
    home = cache / f"packs-{sha[:12]}"
    if (home / ".ok").exists():
        return str(home), f"asset packs {sha[:12]} (shared cache)"
    say("Downloading the asset packs ...")
    tgz = download(url, cache / f"packs-{sha[:12]}.tar.gz", sha, "asset packs")
    tmp = cache / f"packs-{sha[:12]}.unpack"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with tarfile.open(tgz) as t:
        t.extractall(tmp, filter="data")
    (tmp / ".ok").write_text(sha + "\n")
    shutil.rmtree(home, ignore_errors=True)
    tmp.replace(home)
    tgz.unlink()
    return str(home), f"asset packs {sha[:12]} downloaded"


def install_info(url: str) -> dict:
    info = Department(url, "").request("GET", f"/v1/artists/{ARTIST}/install") or {}
    info["_base"] = url
    return info


# ---------------------------------------------------------------------------------------------- git

def git_exclude(project: Path) -> str | None:
    """Keep .oxidegen/ out of git via .git/info/exclude (never the tracked .gitignore). Returns what was done."""
    try:
        r = subprocess.run(["git", "-C", str(project), "rev-parse", "--absolute-git-dir"], capture_output=True,
                           text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode:
        return None
    if subprocess.run(["git", "-C", str(project), "check-ignore", "-q", ".oxidegen/"],
                      capture_output=True).returncode == 0:
        return "git already ignores .oxidegen/"
    excl = Path(r.stdout.strip()) / "info" / "exclude"
    excl.parent.mkdir(parents=True, exist_ok=True)
    text = excl.read_text() if excl.exists() else ""
    excl.write_text(text + ("" if text.endswith("\n") or not text else "\n") + ".oxidegen/\n")
    return f"added .oxidegen/ to {excl} (git won't see the runner's files)"


# ---------------------------------------------------------------------------------------------- the service

LAUNCHER = r'''#!/bin/sh
# oxidegen runner launcher (written by hifipushie-artist setup). Usage: oxidegen-runner-sculpt [--supervise] DIR
# Runs the current version (CACHE/sculpt-current). If an update was switched to and hasn't confirmed (registered)
# within 90 s, rolls back to sculpt-previous first. --supervise restarts it itself (no systemd).
CACHE=$(cd "$(dirname "$0")/.." && pwd)
SUPERVISE=0
[ "$1" = "--supervise" ] && { SUPERVISE=1; shift; }
DIR=$1
# shellcheck source=/dev/null
[ -f "$DIR/runner.env" ] && . "$DIR/runner.env"
export OXIDEGEN_RUNNER_DIR="$DIR" PYTHONUNBUFFERED=1
while :; do
  if [ -f "$DIR/update-pending" ]; then
    age=$(( $(date +%s) - $(stat -c %Y "$DIR/update-pending") ))
    if [ "$age" -gt 90 ] && [ -L "$CACHE/sculpt-previous" ]; then
      echo "launcher: the update never registered; rolling back to $(readlink "$CACHE/sculpt-previous")"
      to=$(sed -n 's/.*"to": *"\([0-9a-f]*\)".*/\1/p' "$DIR/update-pending")
      ln -sfn "$(readlink "$CACHE/sculpt-previous")" "$CACHE/sculpt-current.new" && mv -Tf "$CACHE/sculpt-current.new" "$CACHE/sculpt-current"
      printf '{"%s": {"at": %s, "why": "the new version never started (launcher rollback)"}}\n' "$to" "$(date +%s)" > "$DIR/update-failed.json"
      rm -f "$DIR/update-pending"
    fi
  fi
  "$CACHE/sculpt-current/bin/hifipushie-artist" run --dir "$DIR"
  code=$?
  [ "$code" = 77 ] && exit 77
  [ "$SUPERVISE" = 1 ] || exit "$code"
  sleep 10
done
'''


def _q(s: str) -> str:
    """A systemd unit-file word, double-quoted when needed."""
    s = str(s)
    if re.fullmatch(r"[A-Za-z0-9_./:@+=,-]+", s):
        return s
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def unit_text(launcher: Path, d: Path) -> str:
    return f"""[Unit]
Description=oxidegen {ARTIST} runner (hifipushie) for {d}
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart={_q(launcher)} {_q(d)}
Restart=on-failure
RestartSec=10
# 77: the department refused the token (disconnected): don't restart, run setup again
RestartPreventExitStatus=77
StandardOutput=append:{d / "logs" / "runner.log"}
StandardError=inherit
X-OxidegenRunnerDir={d}

[Install]
WantedBy=default.target
"""


def env_text(blender: str | None, assets: str | None) -> str:
    """runner.env, sourced by the launcher: where Blender and the packs are (no secrets)."""
    lines = ["# written by hifipushie-artist setup"]
    if blender:
        lines.append(f"export HIFIPUSHIE_BLENDER={_shq(blender)}")
        lines.append(f"export PATH={_shq(str(Path(blender).parent))}:\"$PATH\"")
    if assets:
        lines.append(f"export HIFIPUSHIE_ASSETS={_shq(assets)}")
    return "\n".join(lines) + "\n"


def _shq(s: str) -> str:
    return "'" + s.replace("'", "'\\''") + "'"


def systemctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=check, timeout=60)


def has_systemd() -> bool:
    if not shutil.which("systemctl"):
        return False
    try:
        r = systemctl("is-system-running")
    except (OSError, subprocess.SubprocessError):
        return False
    return r.stdout.strip() in ("running", "degraded", "starting", "initializing")


def installed_dir() -> Path | None:
    """The runner dir the user's service points at, if there is one."""
    try:
        m = re.search(r"^X-OxidegenRunnerDir=(.+)$", unit_path().read_text(), re.M)
    except OSError:
        return None
    return Path(m.group(1).strip()) if m else None


def write_launcher() -> Path:
    p = launcher_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(LAUNCHER)
    tmp.chmod(0o755)
    tmp.replace(p)
    return p


def install_service(d: Path) -> Path:
    """Write the launcher and the user unit for runner dir d and enable it (start: start_service)."""
    (d / "logs").mkdir(parents=True, exist_ok=True)
    launcher = write_launcher()
    up = unit_path()
    up.parent.mkdir(parents=True, exist_ok=True)
    up.write_text(unit_text(launcher, d))
    systemctl("daemon-reload")
    systemctl("enable", UNIT)
    return up


def start_service(d: Path, use_systemd: bool) -> str:
    (d / "logs").mkdir(parents=True, exist_ok=True)
    if use_systemd:
        systemctl("restart", UNIT)
        return f"systemd user service {UNIT} (starts at login)"
    stop_nohup(d)
    log = open(d / "logs" / "runner.log", "ab")
    p = subprocess.Popen(["nohup", str(write_launcher()), "--supervise", str(d)], stdout=log, stderr=log,
                         stdin=subprocess.DEVNULL, start_new_session=True)
    (d / "runner.pid").write_text(str(p.pid))
    return f"a background process (pid {p.pid}); it won't survive logging out or a reboot: run setup again"


def stop_nohup(d: Path):
    try:
        pid = int((d / "runner.pid").read_text())
        os.killpg(pid, 15)
    except (OSError, ValueError, ProcessLookupError):
        pass
    (d / "runner.pid").unlink(missing_ok=True)


def uninstall_service() -> bool:
    if not unit_path().exists():
        return False
    systemctl("disable", "--now", UNIT)
    unit_path().unlink()
    systemctl("daemon-reload")
    return True


def wait_online(d: Path, since: float, secs: float = WAIT_ONLINE) -> dict:
    deadline = time.time() + secs
    while time.time() < deadline:
        st = read_json(d / "status.json")
        if st.get("at", 0) >= since and st.get("state") in ("registered", "unauthorized"):
            return st
        time.sleep(0.5)
    return {}


# ---------------------------------------------------------------------------------------------- commands

def _dir(a) -> Path:
    return Path(a.dir).expanduser().resolve() if a.dir else (
        artist.runner_dir() or default_dir().resolve())


def _use(d: Path):
    artist.RUNNER_DIR = d


def cmd_login(a) -> int:
    d = _dir(a)
    _use(d)
    url = a.url or artist.saved_settings().get("url") or DEFAULT_URL
    name = a.name or artist.saved_settings().get("name") or socket.gethostname()
    try:
        tok = redeem(url, a.code, name) if getattr(a, "code", None) else pair(url, name, not a.no_browser)
    except PairingFailed as e:
        say(f"Not connected: {e}. Run the command again for a new code.")
        return 1
    except HTTPError as e:
        say(f"Not connected: the department said {e}")
        return 1
    write_private(artist.token_path(), tok + "\n")
    save_settings(d, url=url, name=name)
    say(f"Connected as {name}")
    return 0


def cmd_logout(a) -> int:
    d = _dir(a)
    _use(d)
    if installed_dir() == d:
        systemctl("disable", "--now", UNIT)
        say(f"stopped {UNIT}")
    stop_nohup(d)
    tp = artist.token_path()
    if tp.exists():
        tp.unlink()
        say(f"removed the token ({tp})")
    else:
        say("no token here")
    return 0


def cmd_install(a) -> int:
    if why := supported():
        say(f"Autostart: {why}. Start the runner yourself: hifipushie-artist run")
        return 1
    d = _dir(a)
    other = installed_dir()
    if other and other != d and not a.move_here:
        say(f"A {ARTIST} runner service already runs for {other}. Use --move-here to point it at {d}.")
        return 0
    up = install_service(d)
    say(f"installed {up} (enabled; `systemctl --user start {UNIT}` or setup starts it)")
    return 0


def cmd_uninstall(a) -> int:
    if why := supported():
        say(f"Autostart: {why}.")
        return 1
    say(f"removed {UNIT}" if uninstall_service() else "no runner service installed")
    return 0


def cmd_status(a) -> int:
    d = _dir(a)
    _use(d)
    st = {"runner_dir": str(d), "token": artist.token_path().exists(), "settings": artist.saved_settings(),
          "service": None, "last_status": read_json(d / "status.json")}
    if not supported() and unit_path().exists():
        st["service"] = {"unit": str(unit_path()), "points_at": str(installed_dir()),
                         "enabled": systemctl("is-enabled", UNIT).stdout.strip(),
                         "active": systemctl("is-active", UNIT).stdout.strip()}
    print(json.dumps(st, indent=1))
    return 0


def cmd_setup(a) -> int:
    if why := supported():
        say(f"Not supported yet: {why}.")
        return 4
    d = _dir(a)
    _use(d)
    project = d.parent.parent if d.parent.name == ".oxidegen" else d
    saved = artist.saved_settings()
    url = a.url or saved.get("url") or DEFAULT_URL
    name = a.name or saved.get("name") or socket.gethostname()
    cache = cache_dir()

    other = installed_dir()
    if other and other != d and not a.move_here:
        st = read_json(other / "status.json")
        say(f"A {ARTIST} runner is already set up for {other} ({st.get('state', 'unknown state')}); it serves this "
            f"project too. To move it here instead: setup --move-here")
        return 0

    # 1. the token
    tp = artist.token_path()
    tok = tp.read_text().strip() if tp.exists() else ""
    if a.code:
        try:
            tok = redeem(url, a.code, name)
        except (HTTPError, RuntimeError) as e:
            say(f"Couldn't redeem the code: {e}")
            return 1
        write_private(tp, tok + "\n")
    elif not (tok and token_works(url, tok)):
        try:
            tok = pair(url, name, not a.no_browser)
        except (PairingFailed, HTTPError) as e:
            say(f"Not connected: {e}")
            return 1
        write_private(tp, tok + "\n")
    say(f"Connected as {name} ({url})")

    # 2. Blender and the packs
    info = install_info(url)
    blender, bnote = ensure_blender(info, cache)
    say(bnote)
    assets, pnote = ensure_packs(info, cache)
    say(pnote)
    git = info.get("git") or {}
    save_settings(d, url=url, name=name, artist=ARTIST, blender=blender, assets=assets,
                  git_repo=git.get("repo") or None)
    (d / "runner.env").write_text(env_text(blender, assets))
    (d / "work").mkdir(parents=True, exist_ok=True)
    if note := git_exclude(project):
        say(note)

    # 3. what this machine can render
    say("Checking what Blender can render here ...")
    probe = artist.gpu_probe(blender=blender)
    (d / "probe.json").write_text(json.dumps(probe, indent=1))

    # 4. the service
    use_systemd = not a.no_autostart and has_systemd()
    since = time.time()
    if use_systemd:
        install_service(d)
    how = start_service(d, use_systemd)
    say(f"Started as {how}")
    if a.no_wait:
        return 0
    st = wait_online(d, since)
    if st.get("state") == "registered":
        say(f"Connected: {name} is ready for sculpting")
        rc = 0
    elif st.get("state") == "unauthorized":
        say(DISCONNECTED)
        return EXIT_UNAUTHORIZED
    else:
        say(f"The runner hasn't reported in yet: see {d / 'logs' / 'runner.log'}")
        rc = 3
    _summary(d, cache, probe, how)
    return rc


def _du(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink()) if p.exists() else 0


def _summary(d: Path, cache: Path, probe: dict, how: str):
    clay = probe.get("workbench") == "ok"
    painted = probe.get("eevee") == "ok"
    say("")
    say(f"  runner:   {d}  ({_du(d) / 1e6:.0f} MB; config, token, logs, workspaces)")
    say(f"  shared:   {cache}  ({_du(cache) / 1e9:.2f} GB; Blender, packs, Python env)")
    say(f"  service:  {how}")
    say(f"  works:    clay looks {'yes' if clay else 'NO'}, painted looks "
        f"{'yes' if painted else 'NO (' + str(probe.get('eevee'))[:80] + ')'}, exports yes")
    say(f"  remove:   curl -fsSL <department>/install/runner.sh | sh -s -- --uninstall [--purge]")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="hifipushie-artist")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, url=True):
        p.add_argument("--dir", help="the runner directory (default ./.oxidegen/runner, or OXIDEGEN_RUNNER_DIR)")
        if url:
            p.add_argument("--url", help=f"the department (default the saved one, else {DEFAULT_URL})")
            p.add_argument("--name", help="this runner's name (default the hostname)")
        return p

    p = common(sub.add_parser("setup", help="connect this computer and start the runner (login + install + start)"))
    p.add_argument("--code", help="a one-time code from the department (else: the browser pairing)")
    p.add_argument("--move-here", action="store_true", help="repoint the user's runner service at this directory")
    p.add_argument("--no-autostart", action="store_true", help="no systemd: a background process instead")
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--no-wait", action="store_true", help=argparse.SUPPRESS)
    p = common(sub.add_parser("login", help="connect this computer (browser pairing, or --code)"))
    p.add_argument("--code")
    p.add_argument("--no-browser", action="store_true")
    common(sub.add_parser("logout", help="forget the token and stop the runner"), url=False)
    p = common(sub.add_parser("install", help="install + enable the systemd user service"), url=False)
    p.add_argument("--move-here", action="store_true")
    common(sub.add_parser("uninstall", help="remove the systemd user service"), url=False)
    common(sub.add_parser("status", help="what's set up here"), url=False)
    a = ap.parse_args(argv)
    return {"setup": cmd_setup, "login": cmd_login, "logout": cmd_logout, "install": cmd_install,
            "uninstall": cmd_uninstall, "status": cmd_status}[a.cmd](a)
