#!/usr/bin/env python3
"""Git guards for the PUBLIC hifipushie repo (installed by bin/install-hooks into the shared .git/hooks).

  guard.py pre-commit          refuse staged paths under workspace/ and staged files over 5 MB
  guard.py pre-push <remote>   (refs on stdin, as git gives them) refuse:
                                 - pushing any ref but main (worker agents never push; the coordinator lands main)
                                 - commits that add files under workspace/ or files over 5 MB
                                 - private-head content: a private-model prefix in an added line, a path or a commit
                                   message of the outgoing commits

Private-model prefixes are NEVER written in a tracked file: they come from $HIFIPUSHIE_PRIVATE_PREFIXES (comma list),
else from the untracked file $HIFIPUSHIE_PRIVATE_PREFIXES_FILE (default /mnt/data/hifipushie/private_prefixes, one per
line or comma separated). With neither, a push is refused (the scan can't run). A prefix matches at a word start,
followed by "_" or a digit, case-sensitive (run tags: "ab" catches ab_3 / ab12, not abc or a variable named ab).
Why: 2026-10-11 a `git add -A` pushed a scratch folder; 2026-10-18 a worker branch with private run tags was pushed.
"""
import os
import re
import subprocess
import sys

MAX_BYTES = 5 * 1024 * 1024
ZERO = "0" * 40
PREFIX_FILE = os.environ.get("HIFIPUSHIE_PRIVATE_PREFIXES_FILE", "/mnt/data/hifipushie/private_prefixes")


def git(*a, check=True) -> str:
    return subprocess.run(["git", *a], capture_output=True, text=True, check=check).stdout


def prefixes() -> list[str] | None:
    raw = os.environ.get("HIFIPUSHIE_PRIVATE_PREFIXES")
    if raw is None and os.path.exists(PREFIX_FILE):
        raw = open(PREFIX_FILE).read()
    if raw is None:
        return None
    return [p.strip() for p in re.split(r"[,\s]+", raw) if p.strip()]


def private_rx(ps: list[str]):
    return re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(p) for p in ps) + r")(?=[_0-9])") if ps else None


def path_faults(paths_sizes) -> list[str]:
    out = []
    for path, size in paths_sizes:
        if path == "workspace" or path.startswith("workspace/"):
            out.append(f"{path}: workspace/ is git-ignored scratch (may hold private heads); never commit it")
        if size is not None and size > MAX_BYTES:
            out.append(f"{path}: {size / 1e6:.1f} MB > 5 MB (big files live on /mnt/data/hifipushie, not in the repo)")
    return out


def _sizes(objs: dict) -> dict:
    """{sha: bytes} for blob shas (one git cat-file --batch-check)."""
    if not objs:
        return {}
    r = subprocess.run(["git", "cat-file", "--batch-check"], input="\n".join(objs) + "\n", capture_output=True,
                       text=True)
    out = {}
    for ln in r.stdout.splitlines():
        p = ln.split()
        if len(p) == 3 and p[1] == "blob":
            out[p[0]] = int(p[2])
    return out


def raw_changes(args: list[str]) -> list[tuple[str, str]]:
    """(path, new blob sha) of added / modified files in a `git diff --raw` / `git log --raw` output."""
    out = []
    for ln in git(*args).splitlines():
        if not ln.startswith(":"):
            continue
        meta, _, path = ln.partition("\t")
        f = meta.split()
        if f[4][0] in "AMCR" and f[3] != ZERO:
            out.append((path.split("\t")[-1], f[3]))
    return out


def pre_commit() -> list[str]:
    ch = raw_changes(["diff", "--cached", "--raw", "--no-abbrev"])
    sz = _sizes({s for _, s in ch})
    return path_faults([(p, sz.get(s)) for p, s in ch])


def pre_push(lines: list[str]) -> list[str]:
    faults = []
    ps = prefixes()
    rx = private_rx(ps or [])
    if ps is None:
        faults.append("private-model prefixes unknown: set HIFIPUSHIE_PRIVATE_PREFIXES or write them (untracked) to "
                      f"{PREFIX_FILE}; the private-content scan can't run")
    for ln in lines:
        p = ln.split()
        if len(p) != 4:
            continue
        lref, lsha, rref, rsha = p
        if lsha == ZERO:  # deleting a remote ref (cleanup of a stray branch): allowed
            continue
        if rref != "refs/heads/main":
            faults.append(f"{rref}: only main is pushed (worker agents never push; the coordinator lands main after the "
                          "privacy scrub)")
        rng = [lsha, "--not", "--remotes"] if rsha == ZERO else [f"{rsha}..{lsha}"]
        ch = raw_changes(["log", "--raw", "--no-abbrev", "--format=", "--no-renames", *rng])
        sz = _sizes({s for _, s in ch})
        faults += path_faults(sorted({(pth, sz.get(s)) for pth, s in ch}))
        if rx:
            for pth, _ in ch:
                if rx.search(pth):
                    faults.append(f"{pth}: a private-model name in a path")
            for m in rx.finditer(git("log", "--format=%B", *rng)):
                faults.append("a commit message names a private model")
                break
            for dl in git("log", "-p", "--no-color", "--format=commit %H", *rng).splitlines():
                if dl.startswith("commit "):
                    cur = dl[7:19]
                elif dl.startswith("+") and not dl.startswith("+++") and rx.search(dl):
                    faults.append(f"commit {cur}: an added line names a private model")
                    break
    return sorted(set(faults), key=faults.index)


def main(argv) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    if mode == "pre-commit":
        faults = pre_commit()
    elif mode == "pre-push":
        faults = pre_push(sys.stdin.read().splitlines())
    else:
        print(__doc__)
        return 2
    if faults:
        print(f"hifipushie {mode} guard REFUSED (bin/hooks/guard.py):", file=sys.stderr)
        for f in faults:
            print("  - " + f, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
