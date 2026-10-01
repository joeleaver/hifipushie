"""A minimal HIP runtime binding (ctypes on the system's libamdhip64.so.7) and the build of field.c for GPU and CPU.

No ROCm SDK, hiprtc, numba-hip, CuPy or PyTorch: the Ubuntu packages libamdhip64-7 + libhsa-runtime64-1 (pulled in by
Mesa/Blender's Cycles HIP) run code objects, and the distro's clang-21 compiles C to amdgcn (gfx1150) directly."""
from __future__ import annotations

import ctypes
import hashlib
import subprocess
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
CLANG = "clang-21"
ARCH = "gfx1150"
COMMON = ["-O3", "-ffp-contract=off", "-fno-fast-math", "-std=c11", "-Wno-unused-function"]


def _variant_flags(real):
    return ["-DREAL=float", "-DREAL_IS_FLOAT"] if real == "float" else []


def build(real="double", target="gpu", src=HERE / "field.c") -> Path:
    BUILD.mkdir(exist_ok=True)
    code = src.read_bytes()
    key = hashlib.sha1(code + f"{real}{target}{COMMON}".encode()).hexdigest()[:12]
    out = BUILD / f"field_{target}_{real}_{key}.{'co' if target == 'gpu' else 'so'}"
    if out.exists():
        return out
    if target == "gpu":
        cmd = [CLANG, f"--target=amdgcn-amd-amdhsa", f"-mcpu={ARCH}", "-nogpulib", *COMMON, *_variant_flags(real),
               "-o", str(out), str(src)]
    else:
        cmd = [CLANG, "-march=native", "-shared", "-fPIC", *COMMON, *_variant_flags(real), "-o", str(out), str(src)]
    t = time.perf_counter()
    subprocess.run(cmd, check=True)
    print(f"  built {out.name} in {time.perf_counter() - t:.1f} s")
    return out


class HipError(RuntimeError):
    pass


class Hip:
    def __init__(self):
        self.h = ctypes.CDLL("libamdhip64.so.7")
        self.h.hipModuleLaunchKernel.argtypes = [ctypes.c_void_p] + [ctypes.c_uint] * 6 + \
            [ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        self.h.hipMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.h.hipFree.argtypes = [ctypes.c_void_p]
        self.h.hipMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        self.h.hipMemGetInfo.argtypes = [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(ctypes.c_size_t)]
        self.h.hipGetErrorString.restype = ctypes.c_char_p
        self.mods = {}
        self.allocated = 0

    def ck(self, r, what=""):
        if r != 0:
            raise HipError(f"{what}: {r} {self.h.hipGetErrorString(r).decode()}")

    def mem_info(self):
        f, t = ctypes.c_size_t(), ctypes.c_size_t()
        self.ck(self.h.hipMemGetInfo(ctypes.byref(f), ctypes.byref(t)), "hipMemGetInfo")
        return f.value, t.value

    def module(self, path):
        path = str(path)
        if path not in self.mods:
            m = ctypes.c_void_p()
            self.ck(self.h.hipModuleLoadData(ctypes.byref(m), Path(path).read_bytes()), "hipModuleLoadData")
            self.mods[path] = (m, {})
        return self.mods[path]

    def function(self, path, name):
        m, fns = self.module(path)
        if name not in fns:
            f = ctypes.c_void_p()
            self.ck(self.h.hipModuleGetFunction(ctypes.byref(f), m, name.encode()), f"hipModuleGetFunction {name}")
            fns[name] = f
        return fns[name]

    def to_device(self, a: np.ndarray) -> "Buf":
        a = np.ascontiguousarray(a)
        b = self.empty(a.nbytes)
        self.ck(self.h.hipMemcpy(b.ptr, a.ctypes.data, a.nbytes, 1), "H2D")
        return b

    def empty(self, nbytes) -> "Buf":
        p = ctypes.c_void_p()
        self.ck(self.h.hipMalloc(ctypes.byref(p), max(int(nbytes), 8)), f"hipMalloc {nbytes}")
        self.allocated += int(nbytes)
        return Buf(self, p, int(nbytes))

    def from_device(self, b: "Buf", dtype, shape):
        out = np.empty(shape, dtype)
        self.ck(self.h.hipMemcpy(out.ctypes.data, b.ptr, out.nbytes, 2), "D2H")
        return out

    def sync(self):
        self.ck(self.h.hipDeviceSynchronize(), "sync")

    def launch(self, fn, n, args, block=256):
        """args: ctypes scalars or Bufs, in the kernel's order."""
        holders = []
        for a in args:
            holders.append(ctypes.c_void_p(a.ptr.value) if isinstance(a, Buf) else a)
        params = (ctypes.c_void_p * len(holders))(*[ctypes.cast(ctypes.byref(h), ctypes.c_void_p) for h in holders])
        grid = (int(n) + block - 1) // block
        self.ck(self.h.hipModuleLaunchKernel(fn, grid, 1, 1, block, 1, 1, 0, None, params, None), "launch")


class Buf:
    def __init__(self, hip, ptr, nbytes):
        self.hip, self.ptr, self.nbytes = hip, ptr, nbytes

    def free(self):
        if self.ptr:
            self.hip.h.hipFree(self.ptr)
            self.hip.allocated -= self.nbytes
            self.ptr = ctypes.c_void_p()


class Cpu:
    """The same kernels compiled for the CPU (one thread): call(name, args) with numpy arrays / ctypes scalars."""

    def __init__(self, path):
        self.lib = ctypes.CDLL(str(path))

    def call(self, name, args):
        conv = [ctypes.c_void_p(a.ctypes.data) if isinstance(a, np.ndarray) else a for a in args]
        getattr(self.lib, name)(*conv)
