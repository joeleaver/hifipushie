"""Extra tools for tests/test_artist.py, loaded into the runner and its worker via HIFIPUSHIE_ARTIST_PRELOAD.

`nap` stands for a long task: it starts a child process (as Blender would be), records both pids, writes a progress
line and sleeps, so a cancel can be seen to kill the whole process group.
"""

from __future__ import annotations

import os
import subprocess
import time

from hifipushie import store
from hifipushie.server import mcp


@mcp.tool(structured_output=False)
def nap(name: str, secs: float = 60.0) -> str:
    """Sleep for a while (a test stand-in for a long export)."""
    child = subprocess.Popen(["sleep", "300"])
    d = store.HOME / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "progress.log").write_text("napping 1/2\nnapping 2/2\n")
    (store.HOME / "nap.pids").write_text(f"{os.getpid()} {child.pid}")
    time.sleep(secs)
    child.kill()
    return "rested"
