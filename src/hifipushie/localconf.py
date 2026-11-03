"""This machine's own settings (not the repo's): a value is $NAME from the environment, else a KEY=VALUE line of the
git-ignored file $HIFIPUSHIE_LOCAL_CONF (default ~/.config/hifipushie/local.env; '#' starts a comment). Where a job runs
(a remote solver route, a host) is a choice of the machine, never of an agent: nothing read here is named in a guide or
a tool description, and code defaults stay local when nothing is set."""
from __future__ import annotations

import os
from pathlib import Path


def path() -> Path:
    return Path(os.environ.get("HIFIPUSHIE_LOCAL_CONF", Path.home() / ".config" / "hifipushie" / "local.env"))


def values() -> dict:
    """The file's KEY=VALUE pairs ({} when there is no file)."""
    out = {}
    try:
        text = path().read_text()
    except OSError:
        return out
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get(name: str, default: str | None = None) -> str | None:
    """$name, else the file's value, else default (an empty value counts as unset)."""
    v = os.environ.get(name)
    if v:
        return v
    return values().get(name) or default


def environ() -> dict:
    """os.environ with the file's values under it (the environment wins): the env for a configured route's command."""
    return {**values(), **os.environ}
