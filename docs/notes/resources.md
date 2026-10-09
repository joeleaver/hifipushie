# hifipushie notes: resources

Moved out of CLAUDE.md on 2026-10-09 so agents don't load every thread's history.

- `resources.py` (2026-09-29, after two OOM crashes of the user's desktop: a terrain export's 16 fork workers x ~2 GB
  plus other agents' jobs): heavy jobs take the machine-wide slot `resources.heavy` (a file lock in $XDG_RUNTIME_DIR;
  $HIFIPUSHIE_HEAVY_SLOTS, default 1) and wait for it; pools are sized by free memory (`resources.workers(per_gb)`:
  half of RAM at most, 12% or 6 GB kept back; $HIFIPUSHIE_MEM_GB) and run under `resources.guarded`, which kills the
  workers and raises MemoryGuardError if free memory falls under half the reserve. Wired into terrain_mesh
  (`_pool`, `export_tiles`), asset (`export`, `flatten_parts`) and blender_asset's worker Blenders. Any new pool or
  batch job must use them, and agents must not run sweeps/exports in parallel with each other.
  Admission by memory (2026-10-07, "slot" agent; the one slot cost hours of hand coordination between sessions, a
  waiting export said "running", the lock wasn't FIFO, and a cancelled export_terrain held it for an hour):
  `resources.heavy(name, log, gb=, kind=, gpu=, model=)` declares a peak (GB; else `estimate(kind, model)` = the
  `KIND_GB` default, RAISED by peaks measured on earlier runs in ~/.cache/hifipushie/heavy_peaks.json, never lowered:
  a pool sized from its grant would measure less each run and shrink itself). Admitted when the running jobs'
  declared peaks + its own fit the budget ($HIFIPUSHIE_HEAVY_GB, default RAM - max(8, RAM/3): 40 GB on this 60 GB
  laptop) and, if others run, what's really free (MemAvailable - reserve - what running jobs declared but don't use
  yet); a lone job always runs. The rule, in order: FIFO by when a job started waiting; a waiting job that doesn't
  fit blocks every younger one, except SMALL ones (<= 25% of the budget) that fit now, and each blocked job can be
  passed at most PASS_LIMIT 3 times (no starvation). GPU jobs (`gpu=True`: local ZOZO; `gpu_claim()` for a GPU
  stage inside a job) run one at a time, FIFO among themselves, and don't block others' memory; an old-code holder
  of heavy0.lock and a job of unknown kind count as holding the GPU (`_holds_gpu`: an old-code ZOZO sim and a new
  one ran on the GPU together and one crashed, 2026-10-07). Path-free view for other machines (S0urc3 through the
  oxidegen sculpt artist): `queue_view` / `queue_text`, MCP tool `heavy_queue` (subject-less, in the artist's
  SUBJECTLESS_OK + FAST; `heavy_status` stays left out): kind, label (`_label`: path words cut to their last part),
  GB, minutes, position, why, GB ahead, and the caller's own jobs marked by `caller_tag` (a hash of
  $HIFIPUSHIE_SESSION or $HIFIPUSHIE_HOME: an artist session's workspace). Wait lines carry no pids and end
  "3rd in queue, 18 GB ahead of you"; export_asset writes them to the model's progress.log, which the artist sends
  as the task's progress. Pools inside a job
  size from its GRANT (`workers()` = min(grant - 1 GB, free memory) / per worker): two jobs both seeing "free" memory
  is how the desktop died. $HIFIPUSHIE_HEAVY_SLOTS=1 brings the one-at-a-time behaviour back.
  State in $HIFIPUSHIE_HEAVY_DIR (default $XDG_RUNTIME_DIR/hifipushie): jobs/<id>.json + jobs/<id>.lock (flocked by
  its owner while alive; a lock anyone can take = a dead owner, swept), all decisions under queue.lock, polled every
  ~1 s (no CPU). Old code's slot heavy0.lock: every new job holds it SHARED (old code's LOCK_EX waits), an old job
  holding it is counted as LEGACY_GB 12. A waiting job logs "waiting for memory: needs X GB, Y of Z declared; held by
  <name (pid, GB, since)>; N ahead of you" (cloth also into its progress); export_asset's reply says how long it
  waited; `resources.status()` / `status_text()` / MCP tool `heavy_status` show running + queue + why.
  Fork safety: every state fd is closed in forked children (`os.register_at_fork`, never LOCK_UN there: the lock
  belongs to the parent's open file description) and is O_CLOEXEC; a forked child of a holder passes through
  `heavy`. Cancellation: server.py runs every sync tool via `anyio.to_thread.run_sync(abandon_on_cancel=True)` under
  `resources.cancel_scope(event)`, set when the call is cancelled or the client goes; then a waiting job leaves the
  queue, and a running one has its `track`ed subprocesses (process groups: `resources.run` replaces subprocess.run
  for Blender in asset / scene / veg_look; cloth Popens tracked) and `guarded` pools killed, `Cancelled` raised IN its
  thread (PyThreadState_SetAsyncExc, once; cleared if the job ends first; `cancel_scope` releases a grant left
  behind), and `profiling.run_jobs/pool_map` check between jobs. `dress`'s background sim thread is not under a cancel
  scope on purpose. Tests: tests/test_heavy.py (+ heavy_job.py), own state dir, ~10 s.

