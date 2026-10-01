#!/bin/sh
# oxidegen sculpt runner installer (hifipushie). Served by the department as /install/runner.sh:
#
#   curl -fsSL <dept>/install/runner.sh | sh -s -- --url <dept> --code <one-time code>
#   ... | sh -s -- --check --url <dept>          fit report only (exit 0 good, 3 works with limits, 4 not a fit)
#   ... | sh -s -- --uninstall [--purge]         remove the service and this project's runner (--purge: the cache)
#
# Options: --project DIR (default: the current directory), --move-here (repoint the user's runner service at this
# project), --no-autostart (no systemd: a background process), --sha SHA / --repo URL (override the department's
# pinned version). Idempotent: running it again upgrades or repairs.
#
# Layout: <project>/.oxidegen/runner/ (config, token, logs, sessions) and the shared
# ${XDG_CACHE_HOME:-~/.cache}/oxidegen/ (uv, Python, tool envs, Blender, packs). Nothing is installed with sudo.
set -u

UV_VERSION=0.10.2
MIN_GLIBC=2.28
ARTIST=sculpt
UNIT="oxidegen-runner-$ARTIST.service"

URL="" CODE="" CHECK=0 UNINSTALL=0 PURGE=0 MOVE=0 NOAUTO=0 PROJECT="" SHA="" REPO=""
while [ $# -gt 0 ]; do
  case "$1" in
    --url) URL=$2; shift ;;
    --code) CODE=$2; shift ;;
    --check) CHECK=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --purge) PURGE=1 ;;
    --move-here) MOVE=1 ;;
    --no-autostart) NOAUTO=1 ;;
    --project) PROJECT=$2; shift ;;
    --sha) SHA=$2; shift ;;
    --repo) REPO=$2; shift ;;
    -h|--help) sed -n '2,16p' "$0" 2>/dev/null || true; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done
URL=${URL%/}
PROJECT=$(cd "${PROJECT:-.}" && pwd) || { echo "no such project directory" >&2; exit 2; }
RUNNER="$PROJECT/.oxidegen/runner"
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/oxidegen"
UNIT_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/$UNIT"

say() { printf '%s\n' "$*" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }
fetch() { # fetch URL [OUT]: to stdout or a file (resuming a .part)
  if have curl; then
    if [ $# -gt 1 ]; then curl -fL --retry 3 -C - -o "$2" "$1"; else curl -fsSL --retry 3 "$1"; fi
  else
    if [ $# -gt 1 ]; then wget -q -c -O "$2" "$1"; else wget -qO- "$1"; fi
  fi
}
json_str() { printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"; }

# ------------------------------------------------------------------------------------------------ uninstall
if [ "$UNINSTALL" = 1 ]; then
  if [ -f "$UNIT_FILE" ]; then
    points=$(sed -n 's/^X-OxidegenRunnerDir=//p' "$UNIT_FILE")
    if [ "$points" = "$RUNNER" ] || [ "$PURGE" = 1 ]; then
      have systemctl && systemctl --user disable --now "$UNIT" >/dev/null 2>&1
      rm -f "$UNIT_FILE"
      have systemctl && systemctl --user daemon-reload >/dev/null 2>&1
      say "removed the service $UNIT"
    else
      say "the service $UNIT serves $points, not this project: left alone (--purge removes it)"
    fi
  fi
  if [ -f "$RUNNER/runner.pid" ]; then kill -- "-$(cat "$RUNNER/runner.pid")" 2>/dev/null; fi
  if [ -d "$RUNNER" ]; then rm -rf "$RUNNER"; rmdir "$PROJECT/.oxidegen" 2>/dev/null; say "removed $RUNNER"; fi
  if [ "$PURGE" = 1 ] && [ -d "$CACHE" ]; then rm -rf "$CACHE"; say "removed the shared cache $CACHE"; fi
  exit 0
fi

# ------------------------------------------------------------------------------------------------ checks
FIT=0 # 0 good, 3 limits, 4 not a fit
NOTES=""
note() { NOTES="$NOTES$1
"; }
limit() { [ "$FIT" -lt 3 ] && FIT=3; note "LIMIT: $1"; }
nofit() { FIT=4; note "NOT A FIT: $1"; }

os=$(uname -s) arch=$(uname -m)
[ "$os" = Linux ] && [ "$arch" = x86_64 ] || nofit "$os $arch isn't supported yet (Linux x86_64 only for now)"

glibc=$(getconf GNU_LIBC_VERSION 2>/dev/null | awk '{print $2}')
if [ -n "$glibc" ]; then
  older=$(printf '%s\n%s\n' "$MIN_GLIBC" "$glibc" | sort -V | head -n1)
  [ "$older" = "$MIN_GLIBC" ] || nofit "glibc $glibc is older than Blender needs ($MIN_GLIBC)"
else
  [ "$os" = Linux ] && nofit "glibc not found (musl distributions can't run the official Blender build)"
fi

# tools the script uses
missing_tools=""
have curl || have wget || missing_tools="$missing_tools curl"
for t in tar sha256sum gzip xz git; do have "$t" || missing_tools="$missing_tools $t"; done

# libraries Blender links (and EGL for headless rendering)
missing_libs=""
if have ldconfig || [ -x /sbin/ldconfig ]; then
  libs=$( (ldconfig -p 2>/dev/null || /sbin/ldconfig -p 2>/dev/null) )
  for l in libGL.so.1 libEGL.so.1 libX11.so.6 libXext.so.6 libXi.so.6 libXfixes.so.3 libXrender.so.1 \
           libXxf86vm.so.1 libxkbcommon.so.0 libSM.so.6 libICE.so.6; do
    printf '%s' "$libs" | grep -q "^[[:space:]]*$l " || missing_libs="$missing_libs $l"
  done
fi
pkg_cmd=""
if [ -n "$missing_tools$missing_libs" ]; then
  if have apt-get; then
    pkgs=""
    for x in $missing_tools $missing_libs; do case $x in
      curl) pkgs="$pkgs curl" ;; tar) pkgs="$pkgs tar" ;; sha256sum) pkgs="$pkgs coreutils" ;; gzip) pkgs="$pkgs gzip" ;;
      xz) pkgs="$pkgs xz-utils" ;; git) pkgs="$pkgs git" ;; libGL.so.1) pkgs="$pkgs libgl1" ;; libEGL.so.1) pkgs="$pkgs libegl1" ;;
      libX11.so.6) pkgs="$pkgs libx11-6" ;; libXext.so.6) pkgs="$pkgs libxext6" ;; libXi.so.6) pkgs="$pkgs libxi6" ;;
      libXfixes.so.3) pkgs="$pkgs libxfixes3" ;; libXrender.so.1) pkgs="$pkgs libxrender1" ;;
      libXxf86vm.so.1) pkgs="$pkgs libxxf86vm1" ;; libxkbcommon.so.0) pkgs="$pkgs libxkbcommon0" ;;
      libSM.so.6) pkgs="$pkgs libsm6" ;; libICE.so.6) pkgs="$pkgs libice6" ;; esac; done
    pkg_cmd="sudo apt-get install -y$pkgs"
  elif have dnf; then
    pkgs=""
    for x in $missing_tools $missing_libs; do case $x in
      curl|tar|gzip|git) pkgs="$pkgs $x" ;; sha256sum) pkgs="$pkgs coreutils" ;; xz) pkgs="$pkgs xz" ;;
      libGL.so.1) pkgs="$pkgs libglvnd-glx" ;; libEGL.so.1) pkgs="$pkgs libglvnd-egl" ;; libX11.so.6) pkgs="$pkgs libX11" ;;
      libXext.so.6) pkgs="$pkgs libXext" ;; libXi.so.6) pkgs="$pkgs libXi" ;; libXfixes.so.3) pkgs="$pkgs libXfixes" ;;
      libXrender.so.1) pkgs="$pkgs libXrender" ;; libXxf86vm.so.1) pkgs="$pkgs libXxf86vm" ;;
      libxkbcommon.so.0) pkgs="$pkgs libxkbcommon" ;; libSM.so.6) pkgs="$pkgs libSM" ;; libICE.so.6) pkgs="$pkgs libICE" ;; esac; done
    pkg_cmd="sudo dnf install -y$pkgs"
  elif have pacman; then
    pkgs=""
    for x in $missing_tools $missing_libs; do case $x in
      curl|tar|gzip|git|xz) pkgs="$pkgs $x" ;; sha256sum) pkgs="$pkgs coreutils" ;;
      libGL.so.1|libEGL.so.1) pkgs="$pkgs libglvnd" ;; libX11.so.6) pkgs="$pkgs libx11" ;; libXext.so.6) pkgs="$pkgs libxext" ;;
      libXi.so.6) pkgs="$pkgs libxi" ;; libXfixes.so.3) pkgs="$pkgs libxfixes" ;; libXrender.so.1) pkgs="$pkgs libxrender" ;;
      libXxf86vm.so.1) pkgs="$pkgs libxxf86vm" ;; libxkbcommon.so.0) pkgs="$pkgs libxkbcommon" ;;
      libSM.so.6) pkgs="$pkgs libsm" ;; libICE.so.6) pkgs="$pkgs libice" ;; esac; done
    # shellcheck disable=SC2086 # (one package per word)
    pkg_cmd="sudo pacman -S --needed$(printf '%s\n' $pkgs | sort -u | tr '\n' ' ' | sed 's/^/ /; s/ $//')"
  else
    pkg_cmd="install with your package manager:$missing_tools$missing_libs"
  fi
  nofit "missing:$missing_tools$missing_libs (run: $pkg_cmd)"
fi

# memory and CPUs
ram_kb=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)
ram_gb=$((ram_kb / 1048576))
cpus=$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 1)
if [ "$ram_kb" -lt 7800000 ]; then nofit "${ram_gb} GB RAM (needs 8 GB; 16 GB for full speed)"
elif [ "$ram_kb" -lt 15600000 ]; then limit "${ram_gb} GB RAM: fewer parallel workers, big exports are slow"; fi
[ "$cpus" -lt 4 ] && limit "$cpus CPU cores: sculpting is CPU-heavy, expect it to be slow"

# Blender already here?
blender_have="" blender_ver=""
for b in "${HIFIPUSHIE_BLENDER:-}" "$(command -v blender 2>/dev/null)" "$CACHE"/blender-*/blender; do
  [ -n "$b" ] && [ -x "$b" ] || continue
  v=$("$b" --background --factory-startup --version 2>/dev/null | sed -n 's/^Blender \([0-9.]*\).*/\1/p' | head -n1)
  case "$v" in 5.1.*) blender_have=$b; blender_ver=$v; break ;; esac
  [ -z "$blender_ver" ] && [ -n "$v" ] && blender_ver="$v (at $b; 5.1 needed)"
done

# disk: the shared cache (Blender if missing, packs, Python env) and the project (sessions)
avail_mb() { d=$1; while [ ! -d "$d" ]; do d=$(dirname "$d"); done; df -Pk "$d" | awk 'NR==2 {print int($4/1024)}'; }
fs_of() { d=$1; while [ ! -d "$d" ]; do d=$(dirname "$d"); done; df -P "$d" | awk 'NR==2 {print $1}'; }
need_cache=$((1500 + 200))
[ -z "$blender_have" ] && need_cache=$((need_cache + 1800))  # 350 MB download + 1.3 GB unpacked
need_project=5000
cache_free=$(avail_mb "$CACHE")
project_free=$(avail_mb "$PROJECT")
if [ "$(fs_of "$CACHE")" = "$(fs_of "$PROJECT")" ]; then
  [ "$cache_free" -lt $((need_cache + need_project)) ] && \
    nofit "disk: ${cache_free} MB free, needs $((need_cache + need_project)) MB (${need_cache} MB tools + ${need_project} MB working room)"
else
  [ "$cache_free" -lt "$need_cache" ] && nofit "disk: ${cache_free} MB free for $CACHE, needs ${need_cache} MB"
  [ "$project_free" -lt "$need_project" ] && nofit "disk: ${project_free} MB free in the project, needs ${need_project} MB"
fi

# GPU: painted looks render in EEVEE (any real GPU); clay looks work on CPU too
gpu=none gpu_name=""
if have nvidia-smi && nvidia-smi -L >/dev/null 2>&1; then
  gpu=nvidia gpu_name=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -n1)
elif [ -e /dev/kfd ] || (have rocminfo && rocminfo >/dev/null 2>&1); then gpu=amd
elif ls /dev/dri/renderD* >/dev/null 2>&1; then gpu=other
fi
painted=likely
[ "$gpu" = none ] && { painted=no; limit "no GPU found: clay looks work, painted looks (EEVEE) won't"; }

# systemd --user
systemd=no
if have systemctl; then
  case "$(systemctl --user is-system-running 2>/dev/null)" in running|degraded|starting|initializing) systemd=yes ;; esac
fi
[ "$systemd" = no ] && limit "no systemd user session: the runner runs as a background process that won't survive logout (--no-autostart)"

# existing service
service_dir=""
[ -f "$UNIT_FILE" ] && service_dir=$(sed -n 's/^X-OxidegenRunnerDir=//p' "$UNIT_FILE")

# the department
dept=skipped
if [ -n "$URL" ]; then
  if INFO=$(fetch "$URL/v1/artists/$ARTIST/install" 2>/dev/null) && [ -n "$INFO" ]; then dept=ok
  else dept=unreachable; nofit "the department at $URL isn't reachable"; fi
fi

report() {
  printf '{"fit": %s, "os": %s, "arch": %s, "glibc": %s, "ram_gb": %s, "cpus": %s, "gpu": %s, "gpu_name": %s, ' \
    "$FIT" "$(json_str "$os")" "$(json_str "$arch")" "$(json_str "$glibc")" "$ram_gb" "$cpus" "$(json_str "$gpu")" "$(json_str "$gpu_name")"
  printf '"painted_looks": %s, "disk_free_mb": {"cache": %s, "project": %s}, "disk_needed_mb": {"cache": %s, "project": %s}, ' \
    "$(json_str "$painted")" "${cache_free:-0}" "${project_free:-0}" "$need_cache" "$need_project"
  printf '"missing_tools": %s, "missing_libs": %s, "install_command": %s, "systemd_user": %s, "department": %s, ' \
    "$(json_str "${missing_tools# }")" "$(json_str "${missing_libs# }")" "$(json_str "$pkg_cmd")" "$( [ $systemd = yes ] && echo true || echo false)" "$(json_str "$dept")"
  printf '"blender": %s, "blender_path": %s, "existing_service_dir": %s, "notes": %s}\n' \
    "$(json_str "$blender_ver")" "$(json_str "$blender_have")" "$(json_str "$service_dir")" "$(json_str "$(printf '%s' "$NOTES" | tr '\n' ';')")"
}
summary() {
  case $FIT in 0) say "Fit: good." ;; 3) say "Fit: works, with limits." ;; *) say "Fit: not a fit (yet)." ;; esac
  say "  $os $arch, glibc ${glibc:-?}, ${ram_gb} GB RAM, $cpus cores, GPU: $gpu ${gpu_name:+($gpu_name)}"
  say "  disk free: cache ${cache_free} MB (needs ${need_cache}), project ${project_free} MB (needs ${need_project})"
  say "  Blender: ${blender_ver:-not installed (will be downloaded)}; systemd user: $systemd; department: $dept"
  [ -n "$service_dir" ] && say "  a runner service already exists for $service_dir"
  printf '%s' "$NOTES" | while IFS= read -r l; do [ -n "$l" ] && say "  - $l"; done
}

if [ "$CHECK" = 1 ]; then report; summary; exit "$FIT"; fi
if [ "$FIT" = 4 ]; then summary; say "Not installing. Fix the above and run this again."; exit 4; fi
[ -n "$URL" ] || { say "--url <department> is required"; exit 2; }
summary

# ------------------------------------------------------------------------------------------------ install
set -e
mkdir -p "$CACHE/bin" "$RUNNER"
export UV_CACHE_DIR="$CACHE/uv" UV_PYTHON_INSTALL_DIR="$CACHE/python" UV_NO_MODIFY_PATH=1

# 1. uv (pinned, sha256-checked)
UV="$CACHE/bin/uv"
if ! [ -x "$UV" ] || ! "$UV" --version 2>/dev/null | grep -q " $UV_VERSION"; then
  say "Installing uv $UV_VERSION ..."
  tarball="uv-x86_64-unknown-linux-gnu.tar.gz"
  base="https://github.com/astral-sh/uv/releases/download/$UV_VERSION"
  tmp=$(mktemp -d "$CACHE/uv-dl.XXXXXX")
  fetch "$base/$tarball" "$tmp/$tarball"
  want=$(fetch "$base/$tarball.sha256" | awk '{print $1}')
  got=$(sha256sum "$tmp/$tarball" | awk '{print $1}')
  [ -n "$want" ] && [ "$want" = "$got" ] || { say "uv download: sha256 $got != $want"; rm -rf "$tmp"; exit 1; }
  tar -xzf "$tmp/$tarball" -C "$tmp"
  mv -f "$tmp/uv-x86_64-unknown-linux-gnu/uv" "$UV"
  rm -rf "$tmp"
fi

# 2. which hifipushie: the department's pinned git sha (or --sha/--repo)
if [ -z "$SHA" ]; then
  [ -n "${INFO:-}" ] || INFO=$(fetch "$URL/v1/artists/$ARTIST/install")
  printf '%s' "$INFO" > "$CACHE/install.json"
  SHA=$("$UV" run --no-project --python 3.12 python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["git"]["sha"])' "$CACHE/install.json")
  [ -n "$REPO" ] || REPO=$("$UV" run --no-project --python 3.12 python -c \
    'import json,sys; print(json.load(open(sys.argv[1]))["git"].get("repo") or "")' "$CACHE/install.json")
fi
[ -n "$REPO" ] || REPO=https://github.com/joeleaver/hifipushie

# 3. the code: its own tool env per sha, side by side (the runner's self-update uses the same layout)
TOOLS="$CACHE/tools/$SHA"
if ! [ -x "$TOOLS/bin/hifipushie-artist" ]; then
  say "Installing hifipushie $SHA from $REPO ..."
  UV_TOOL_DIR="$TOOLS" UV_TOOL_BIN_DIR="$TOOLS/bin" "$UV" tool install --force --python 3.12 "git+$REPO@$SHA" >&2
fi
cur=$(readlink "$CACHE/$ARTIST-current" 2>/dev/null || true)
if [ "$cur" != "tools/$SHA" ]; then
  [ -n "$cur" ] && ln -sfn "$cur" "$CACHE/$ARTIST-previous"
  ln -sfn "tools/$SHA" "$CACHE/$ARTIST-current"
fi

# 4. connect, Blender, packs, the service: the runner's own setup
set -- setup --url "$URL" --dir "$RUNNER"
[ -n "$CODE" ] && set -- "$@" --code "$CODE"
[ "$MOVE" = 1 ] && set -- "$@" --move-here
{ [ "$NOAUTO" = 1 ] || [ "$systemd" = no ]; } && set -- "$@" --no-autostart
exec "$CACHE/$ARTIST-current/bin/hifipushie-artist" "$@"
