#!/usr/bin/env python3
"""Run bundle jobs on oxidegen's GPU fleet from the command line (docs/bundle-jobs.md). Standard library only.

  bundle_client.py run --bundle zozo --runner cloth_zozo.py [--outputs out.npz] [--batch NAME] [--pull DIR]
                       [--timeout-minutes 120] [--no-wait] JOB_DIR...
      Tars each job folder, uploads it (signed PUT links), submits the batch, then (unless --no-wait) follows it:
      prints each job's progress line as it changes and downloads each finished job's outputs to
      DIR/<job>/<output> (default DIR = ./results/<batch name>). Exits 0 when every job succeeded, 1 otherwise.
  bundle_client.py status BATCH        the batch as JSON
  bundle_client.py wait BATCH [--pull DIR]   follow it (and pull) until every job has ended
  bundle_client.py pull BATCH DIR      download every finished job's outputs
  bundle_client.py cancel BATCH        stop its unfinished jobs
  bundle_client.py list                your recent batches
  bundle_client.py bundles             the named bundles

Auth: OXIDEGEN_TOKEN (a bearer token, e.g. an agent token from the web console), OXIDEGEN_URL (default
https://oxidegen.jkbase.app). Only admins and research users may run bundle jobs.
"""
import argparse
import io
import json
import os
import sys
import tarfile
import time
import urllib.error
import urllib.request

URL = os.environ.get("OXIDEGEN_URL", "https://oxidegen.jkbase.app").rstrip("/")
TERMINAL = {"succeeded", "failed", "canceled"}


# The platform's front door answers 502/503/504 now and then (a restart, a hiccup): such a request is tried again.
RETRY_CODES = {502, 503, 504}
RETRY_WAITS = (2, 5, 15, 30, 60)


def send(req, timeout, retry=True):
    """urlopen with retries on a gateway error or a dropped connection → the parsed JSON. `retry=False` for a
    request that must not be repeated (submitting a batch: a 502 may hide one that went through)."""
    for i, wait in enumerate((0,) + (RETRY_WAITS if retry else ())):
        time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if not retry or e.code not in RETRY_CODES or i == len(RETRY_WAITS):
                raise
            print(f"  {req.get_method()} got {e.code}; trying again in {RETRY_WAITS[i]} s", file=sys.stderr, flush=True)
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if not retry or i == len(RETRY_WAITS):
                raise
            print(f"  {req.get_method()} failed ({e}); trying again in {RETRY_WAITS[i]} s", file=sys.stderr, flush=True)


def api(method, path, body=None):
    token = os.environ.get("OXIDEGEN_TOKEN")
    if not token:
        sys.exit("set OXIDEGEN_TOKEN")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        # a GET, or asking for upload links (harmless twice), is retried; submitting / cancelling is not
        return send(req, 120, retry=method == "GET" or path.endswith("/uploads"))
    except urllib.error.HTTPError as e:
        if method == "POST" and path == "/v1/bundle-jobs" and e.code in RETRY_CODES:
            sys.exit(f"submit got {e.code}: it may or may not have gone through; check `bundle_client.py list` before submitting again")
        sys.exit(f"{method} {path}: {e.code} {e.read().decode(errors='replace')[:600]}")


def put(url, data):
    """PUT a file to a signed upload link (a re-PUT replaces it, so retrying is safe)."""
    req = urllib.request.Request(url, data=data, method="PUT", headers={"Content-Type": "application/octet-stream"})
    return send(req, 600)


def tar_folder(path):
    """The job folder as .tar.gz bytes (members under <name>/)."""
    path = os.path.abspath(path.rstrip("/"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(path, arcname=os.path.basename(path))
    return buf.getvalue()


def pull(batch_view, dest, have):
    """Download each finished job's outputs not yet in `have`; returns how many it fetched."""
    n = 0
    for j in batch_view["jobs"]:
        for o in j.get("outputs") or []:
            key = (j["name"], o["name"])
            if key in have or not o.get("url"):
                continue
            target = os.path.join(dest, j["name"], o["name"])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with urllib.request.urlopen(o["url"], timeout=600) as r, open(target + ".part", "wb") as f:
                f.write(r.read())
            os.replace(target + ".part", target)
            have.add(key)
            n += 1
            print(f"[{j['name']}] pulled {target}", flush=True)
    return n


def follow(batch, dest, poll=30):
    have, seen = set(), {}
    while True:
        v = api("GET", f"/v1/bundle-jobs/{batch}")
        for j in v["jobs"]:
            line = f"{j['state']}" + (f" — {j['progress']}" if j.get("progress") else "")
            if j["state"] == "failed" and j.get("error"):
                line += f"\n    {j['error']}"
            if seen.get(j["name"]) != line:
                seen[j["name"]] = line
                print(f"[{j['name']}] {line}", flush=True)
        if dest:
            pull(v, dest, have)
        if all(j["state"] in TERMINAL for j in v["jobs"]):
            print(f"batch {v['state']}: {json.dumps(v['counts'])}, ${v['cost_usd']:.4f}", flush=True)
            return v
        time.sleep(poll)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--bundle", required=True, help="a bundle name (bundles) or a JSON registration")
    r.add_argument("--runner", required=True, help="the runner script")
    r.add_argument("--outputs", default="out.npz", help="comma-separated paths inside each job folder")
    r.add_argument("--batch", help="a name for the batch")
    r.add_argument("--pull", help="where outputs go (default ./results/<batch name>)")
    r.add_argument("--timeout-minutes", type=int, default=120)
    r.add_argument("--no-wait", action="store_true")
    r.add_argument("jobs", nargs="+", help="job folders")
    for name in ("status", "cancel"):
        sub.add_parser(name).add_argument("batch")
    w = sub.add_parser("wait")
    w.add_argument("batch")
    w.add_argument("--pull")
    p = sub.add_parser("pull")
    p.add_argument("batch")
    p.add_argument("dest")
    sub.add_parser("list")
    sub.add_parser("bundles")
    a = ap.parse_args()

    if a.cmd == "run":
        names = [os.path.basename(os.path.abspath(j.rstrip("/"))) for j in a.jobs]
        runner_name = os.path.basename(a.runner)
        files = [f"{n}.tar.gz" for n in names] + [runner_name]
        ups = api("POST", "/v1/bundle-jobs/uploads", {"files": files})["uploads"]
        keys = {}
        for job_dir, n, u in zip(a.jobs, names, ups):
            data = tar_folder(job_dir)
            put(u["put_url"], data)
            keys[n] = u["key"]
            print(f"[{n}] uploaded {len(data) / 1e6:.1f} MB", flush=True)
        with open(a.runner, "rb") as f:
            put(ups[-1]["put_url"], f.read())
        bundle = json.loads(a.bundle) if a.bundle.strip().startswith("{") else a.bundle
        batch_name = a.batch or time.strftime("batch-%Y%m%d-%H%M%S")
        v = api("POST", "/v1/bundle-jobs", {
            "bundle": bundle, "runner": {"name": runner_name, "key": ups[-1]["key"]},
            "jobs": [{"name": n, "folder": keys[n]} for n in names],
            "outputs": [o.strip() for o in a.outputs.split(",") if o.strip()],
            "batch": batch_name, "timeout_minutes": a.timeout_minutes})
        print(f"batch {v['batch']} ({batch_name}): {len(v['jobs'])} jobs", flush=True)
        if a.no_wait:
            return
        v = follow(v["batch"], a.pull or os.path.join("results", batch_name))
        sys.exit(0 if v["state"] == "done" else 1)
    if a.cmd == "status":
        print(json.dumps(api("GET", f"/v1/bundle-jobs/{a.batch}"), indent=1))
    elif a.cmd == "wait":
        v = follow(a.batch, a.pull)
        sys.exit(0 if v["state"] == "done" else 1)
    elif a.cmd == "pull":
        pull(api("GET", f"/v1/bundle-jobs/{a.batch}"), a.dest, set())
    elif a.cmd == "cancel":
        print(json.dumps(api("POST", f"/v1/bundle-jobs/{a.batch}/cancel"), indent=1))
    elif a.cmd == "list":
        print(json.dumps(api("GET", "/v1/bundle-jobs"), indent=1))
    elif a.cmd == "bundles":
        print(json.dumps(api("GET", "/v1/bundles"), indent=1))


if __name__ == "__main__":
    main()
