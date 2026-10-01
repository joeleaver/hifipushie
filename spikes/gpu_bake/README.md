# GPU bake spike (2026-10-01)

Question: can the terrain tile map bake (`terrain_bake`: texels projected onto the exact rock field, then normal,
height, AO, colour, weights, lines) run on the Radeon 890M much faster than the compiled CPU path (`fieldjit`, numba)?

**Answer: no-go for now.** The GPU works and fp64 kernels are bit-identical to numba, but in fp64 the field's heaviest
leaf (jointed blocks) runs at half the CPU pool's rate. fp32 is 4-12x the pool, but it is a different field: every term
needs a precision audit (one bug moved joints 5 cm). Most of the composition is not ported yet either. End to end, an
export would gain about 1.1x (alps) to 1.4x (pebble) at best. See "Recommendation".

## What runs here

| path | state |
|---|---|
| ROCm SDK (hipcc, hiprtc, rocminfo) | not installed |
| HIP runtime | **works**: Ubuntu's `libamdhip64-7` 7.1 + `libhsa-runtime64-1` (the ones Blender's Cycles HIP uses), `/dev/kfd`, user in `render` |
| compiler | **works**: the distro's `clang-21` targets `amdgcn-amd-amdhsa -mcpu=gfx1150` straight from C (`-nogpulib`) |
| Vulkan | RADV (Mesa 26) works; `glslc`/`glslangValidator` installed; not needed |
| OpenCL | ICD loader only, no platform (no `/etc/OpenCL/vendors`) |
| numba-hip / CuPy-ROCm / PyTorch-ROCm | not tried: all need a ROCm SDK or ship one (GBs); the path above needs nothing |

So nothing was installed. `hip.py` is about 130 lines of ctypes over `libamdhip64.so.7`: module load, malloc, memcpy and
launch. `field.c` is compiled twice by the same clang: once for the GPU (a code object), once for the CPU (a .so).

## The prototype

`field.c` is one C source with kernels transcribed from `fieldjit.py`, operation by operation, without FMA contraction
(`-ffp-contract=off`):
- `k_column`: Field.column (the 5-tap cubic B-spline) plus steep, grain and face_dir;
- `k_fbm`: noise.fbm;
- `k_facets`: terrain_facets.facets. Triangulations are built on the CPU (scipy, cached) and packed into one pool with a
  hash table keyed by (seed+axis, block). Point location uses the bucket grid and walk. Points within 1e-9 of an edge
  are flagged for the host, which finishes them with scipy's chained walk;
- `k_blocks`: terrain_blocks' bed coordinate plus offsets with the maps' sharp window. The heaviest leaf.

The workload is `dump_workload.py`: the alps bake field (`CliffField.front_field()` with micro relief), plus 250k
texel-like points on the steepest face (8/m in plan, ±15 cm about the surface, Morton ordered).

## Results (alps, 250k points)

**Agreement** (`agree.py`):
- fp64 on the GPU matches numba bit for bit on column+grids, blocks and facets: 0 of 1.5M / 1M / 750k values differ, and
  no facet point was ambiguous. The CPU build of the same C is also bit-identical, both to numba and to the GPU.
- fbm differs from numba by ~1e-12. numpy does `q @ R` through BLAS (FMA), while the C does plain mul/add. GPU and CPU C
  agree with each other.
- fp32 differs. Value errors: column h p99 0.25 mm (the float32 height grid); blocks offsets p99 0.12 mm, max 1.2 mm;
  facets p99 4e-4 (x their 6 cm amplitude).
- The first fp32 port moved joints by up to 5 cm. The bed thickness `(K + c1) - (K + c0)` cancels ~3e-5 at K ~ 300, the
  joint spacing derives from it, and the joint coordinate counts ~1000 spacings from the world origin. Taking the
  thickness from the cuts table fixed it. Every term of a float port needs this kind of audit.

**What fp32 does to the maps** (`normals.py`; a composed rock field F = ground + steep x (facets x3 + sharp blocks)):

| | value mm p50 / p99 / max | normal deg p50 / p99 / max (h = 3 cm) | 8-bit normal texels differing | (h = 0.4 m) |
|---|---|---|---|---|
| fp32, world z | 0.044 / 0.21 / 0.58 | 0.051 / 0.17 / 0.53 | 17% (by 1 LSB) | 1.8% |
| fp32, z and H relative to the tile | 0.030 / 0.20 / 0.60 | 0.024 / 0.14 / 0.52 | 10% | 1.3% |

The visible effect is nil: 1 LSB is about 0.45 deg. But an export would no longer be byte-identical, which is today's
test for every field change. The decimation reacts to 1e-15 changes (CLAUDE.md), so LODs would re-roll.

**Determinism** (`determinism.py`): the same point gives the same bits in fp64 and fp32, whatever the batch (shuffled
order, 777-point batches). Tile borders are safe as long as every tile goes through the same path. A CPU fallback for
some points (for example ambiguous facets) is exact in fp64 but not in fp32.

**Throughput** (`throughput.py`; million points/s, kernel time only, a loaded shared laptop, two runs):

| kernel | numba x1 | numba pool (12) | same C, 1 CPU thread | GPU fp64 | GPU fp32 | GPU fp64 / pool | GPU fp32 / pool |
|---|---|---|---|---|---|---|---|
| column + 4 grids | 7.7 | 22 | 10.8 | 91 | 500 | 4.1 | 23 |
| fbm (3 octaves) | 6.9 | 53 | 9.9 | 117 | 616 | 2.2 | 12 |
| **blocks** (bed coord + offsets, sharp) | 1.07 | **6.6** | 1.16 | **3.2** | **29** | **0.49** | 4.4 |
| facets 15 m | 16 | 82 | 38 | 282 | 993 | 3.4 | 12 |
| facets 4.5 m | 15.5 | 74 | 34 | 371 | 869 | 5.0 | 12 |
| facets 1.2 m | 12.8 | 71 | 25 | 351 | 777 | 4.9 | 11 |

- Blocks are ~55-60% of the bake field's CPU time (alps export profile: field.blocks 190 of 322 s in `_job_bake`). In
  fp64 they run at **half** the pool's rate: RDNA 3.5 does fp64 at a small fraction of fp32. Removing the kernel's 500
  B/lane of scratch (local arrays, 128-VGPR cap) didn't change that.
- Contention (`contention.py`): CPU and GPU share package power and memory bandwidth. With the 12-worker pool busy, GPU
  fp32 blocks fell from 16.3 to 10.3 M/s (uploads included). fp64 held at 2.4-2.5 M/s, and GPU plus pool came to 7.6 M/s
  against 5.4 for the pool alone: the GPU as a 13th worker gives +40%.
- The same C on one CPU thread beats numba by 1.1x on blocks and 2-2.4x on facets (numba's facets dispatch blocks from
  Python).

**Memory on the shared-RAM iGPU**: `hipMalloc` comes out of GTT (54 GB; the VRAM carve-out is 2 GB and the desktop
already holds 1.9 GB of it). A filled 2 GB buffer moved `mem_info_gtt_used` by +2.0 GB and process PSS by 0.
`resources.peak_memory` and `guarded` count PSS, so they would not see GPU memory. Any integration must read
`/sys/class/drm/card1/device/mem_info_gtt_used`. A bake's device data is small: grids about 5 x 4 MB (alps 801 x 601),
triangulations about 0.2 MB each, and ~60 B per point.

**Desktop**: kernels of up to ~0.3 s (1M points of fp64 blocks) ran with no hang or GPU reset in the kernel log. Desktop
smoothness wasn't observed. The compositor shares this GPU, so batches should stay under ~50 ms (fp32 blocks: ~1M
points).

## What it would take

- **Port the rest of the field composition.** Ported here: ~520 lines of C. Still in numpy: rock_relief's glue,
  bed_planes/_bed_noise, _joints, the blocks' ids/masters/carve (logaddexp needs our own exp/log in C), micro_relief,
  fallen_sd, Tube.sd for volumes (with _pl_walk), CliffField.front/Region.s/voids, the Newton loop (one kernel per
  texel), Materials.weights + block_colour + structure_lines for the colour, weights and lines maps, and AO. Estimate
  ~2500-3500 lines of C, on top of keeping the numba path.
- **Keep one source.** `field.c` already shows the way: the same C compiled for CPU and GPU, bit-identical in fp64. Make
  the C the reference and call it from the CPU path too (ctypes/cffi), instead of numba plus numpy plus a GPU copy. A
  float variant is a `-DREAL=float` build plus `#ifdef REAL_IS_FLOAT` reformulations where precision bites.
  `tests/test_fieldjit.py`-style checks then compare C-fp64 with numba bit for bit, and fp32 with tolerances (mm, deg).
- **Integration.** HIP must not be initialised before the fork pool forks; one process should own the GPU, with workers
  sending batches (or the parent runs the GPU pass per atlas piece). Triangulations would be built once and shared, not
  cold per worker (today 6% of the bake: 19.5 of 322 s, alps). The memory guard must count GTT, and batches must be
  small for the desktop.

## Meshing too?

Yes, the same field kernels serve meshing: the MC lattice (Field.value without micro) and the dense projection are
regular, coherent point sets. Meshing then needs determinism, which holds per point in both precisions, rather than
fp64. In the export profiles meshing is about as much field work as the bake: pebble MC 268 + dense 280 busy-s against
the bake's 588 s of field. In fp32 the meshed surface changes, so decimation re-rolls and byte-identical exports are
gone.

## Bake in Blender/Cycles instead?

Not worth it:
- Cycles bakes selected-to-active from a mesh. Our maps come from the exact field: micro relief below the meshing voxel,
  band-limited per LOD, the sharp structure window, creases kept out of the geometry. A high mesh carrying that would
  need ~5 cm voxels per LOD band, which means evaluating the field at more points than the texels themselves.
- Normals would come from a mesh, not the gradient.
- Colour, weights and lines come from numpy logic over block/bed ids (Materials, block_colour, structure_lines). That
  would mean reimplementing them as nodes or fine vertex attributes.
- Tile borders agree today because every texel is pointwise exact. Ray-cast bakes from different low polys at a shared
  border don't have that.
- Cycles HIP on this iGPU was no faster than the 12 cores for AO (175 s vs 168 s, CLAUDE.md 2026-09-23).
- It fits characters with node materials (4.4 s vs 758 s there), not this.

## Recommendation

**No-go on a GPU bake now.** Expected end-to-end export speed-up if done fully:

| | alps 3x3 (131 s) | pebble (227 s) |
|---|---|---|
| bake field only, fp32 | ~1.05x: the tiles stage waits on a 65 s decimation straggler | ~1.15x (227 -> ~198 s) |
| whole field (MC, dense, tiles, bake), fp32 | ~1.1x | ~1.4x (field ~60% of busy CPU at ~3.3x under contention) |
| fp64 (exports stay byte-identical) | no gain | at most ~1.1x, GPU as an extra worker |

Risks:
- a second implementation of ~3000 lines to keep in sync;
- fp32 means giving up byte-identical exports and auditing every term for cancellation (one 5 cm bug found);
- HIP and fork-pool integration;
- a memory guard that can't see GTT;
- desktop stalls from long kernels;
- the APU's shared power, which makes CPU and GPU slow each other down.

Better levers first:
1. The alps critical path is decimation (`_job_tile` 65 s), not the bake.
2. Move the field's numpy glue into compiled code. The same-C CPU build beat numba 1.1-2.4x per leaf, and the glue is
   ~20-40% of field time. Doing it in one C source keeps fp64 bit-identity and leaves a GPU build available later.
3. Build triangulations once per export and share them, instead of cold misses in every worker.

Revisit the GPU when the whole field is one compiled source, or if a mixed-precision blocks kernel (coordinates in fp64,
windows and noise in fp32) gets near fp32 speed with sub-mm error.

## Files

- `field.c`: the kernels (GPU + CPU, fp64/fp32 from one source).
- `hip.py`: ctypes HIP runtime + build.
- `bench.py`: inputs, runners, numba references.
- `dump_workload.py`: builds the alps field, profiles numba, dumps the workload (`work_alps.npz`, ~55 MB, git-ignored).
- `agree.py`, `normals.py`, `throughput.py`, `contention.py`, `determinism.py`: the measurements above.

Run order: `uv run python spikes/gpu_bake/dump_workload.py alps 250000`, then the others with `uv run python
spikes/gpu_bake/<script>.py` from the repo root or this directory. Heavy runs take `resources.heavy`.
