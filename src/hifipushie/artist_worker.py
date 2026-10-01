"""The artist runner's worker: one subprocess per session that runs hifipushie's tools (see artist.py).

It is started by the runner with HIFIPUSHIE_HOME = the session's workspace and HIFIPUSHIE_NO_LIVE=1, in its own
process group, so a cancel can kill it together with every Blender it started. It serves JSON lines: requests on
stdin, one reply per request on the file descriptor the runner passes as argv[1] (fd 1 is pointed at stderr before
hifipushie is imported, so nothing a tool prints can corrupt the replies).

Requests:
  {"op": "call", "tool": t, "args": {...}, "out": dir}  -> {"ok": true, "content": [{"type": "text", "text"} |
                                                           {"type": "image", "path", "mime"}]} | {"ok": false, "error"}
      Runs the tool through the MCP server's own call path (mcp.call_tool), so argument validation and error text
      are hifipushie's; images are written into `out` instead of travelling back as base64.
  {"op": "hydrate", "kind": "model" | "terrain", "name": n, "spec": {...}, "note": s}  -> {"ok": true, "text"}
  {"op": "ping"} -> {"ok": true}
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import json
import os
import sys
from pathlib import Path


def _content(result, out: Path) -> list[dict]:
    items = []
    for i, c in enumerate(getattr(result, "content", None) or []):
        kind = getattr(c, "type", None)
        if kind == "text":
            items.append({"type": "text", "text": c.text})
        elif kind == "image":
            mime = getattr(c, "mimeType", None) or getattr(c, "mime_type", None) or "image/png"
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "bin")
            p = out / f"content_{i}.{ext}"
            p.write_bytes(base64.b64decode(c.data))
            items.append({"type": "image", "path": str(p), "mime": mime})
        else:  # (no hifipushie tool returns other kinds; say so rather than drop it)
            items.append({"type": "text", "text": f"[{kind} content not relayed]"})
    return items


def _error_text(e: BaseException) -> str:
    text = str(e)
    prefix = "Error executing tool "  # the SDK's wrapper; hifipushie's own text follows the tool name
    if text.startswith(prefix) and ": " in text:
        text = text.split(": ", 1)[1]
    return text or type(e).__name__


def serve(reply_fd: int) -> None:
    for mod in filter(None, os.environ.get("HIFIPUSHIE_ARTIST_PRELOAD", "").split(",")):
        importlib.import_module(mod)  # (tests register extra tools this way)
    from .server import mcp
    replies = os.fdopen(reply_fd, "w", buffering=1)

    def send(obj):
        replies.write(json.dumps(obj) + "\n")
        replies.flush()

    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        try:
            op = req["op"]
            if op == "ping":
                send({"ok": True})
            elif op == "call":
                out = Path(req["out"])
                out.mkdir(parents=True, exist_ok=True)
                result = asyncio.run(mcp.call_tool(req["tool"], req["args"]))
                if getattr(result, "isError", False) or getattr(result, "is_error", False):
                    text = " ".join(c.text for c in result.content if getattr(c, "type", "") == "text")
                    send({"ok": False, "error": text or "the tool failed"})
                else:
                    send({"ok": True, "content": _content(result, out)})
            elif op == "hydrate":
                if req["kind"] == "terrain":
                    from . import terrain_tools
                    v = terrain_tools.save(req["name"], req["spec"], req.get("note", "hydrated"))
                else:
                    from . import store
                    v = store.save(req["name"], req["spec"], req.get("note", "hydrated"))
                send({"ok": True, "text": f"{req['kind']} {req['name']} v{v}"})
            else:
                send({"ok": False, "error": f"unknown op {op!r}"})
        except BaseException as e:  # (a tool's failure is a reply, never the worker's end)
            if isinstance(e, (KeyboardInterrupt, SystemExit)):
                raise
            send({"ok": False, "error": _error_text(e)})


def main() -> None:
    reply_fd = int(sys.argv[1])
    os.dup2(2, 1)  # tool chatter on stdout goes to stderr; replies have their own fd
    sys.stdout = sys.stderr
    serve(reply_fd)


if __name__ == "__main__":
    main()
