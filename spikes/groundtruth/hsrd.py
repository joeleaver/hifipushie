"""groundtruth: HSRD-100's rig. Each photo has a RealityCapture .xmp (xcr 1.1): Rotation (world -> camera, row-major;
camera x right, y down, z forward), Position (the camera's centre, the scan's metres), FocalLength35mm,
PrincipalPointU / V and brown3 radial distortion (k1 k2 k3), the last three in units of the 35 mm frame normalised by
the picture's LONGER side: f_px = f35 / 36 * max(w, h); pp_px = (w / 2 + U * max(w, h), h / 2 + V * max(w, h));
x_d = x (1 + k1 r^2 + k2 r^4 + k3 r^6) on x = X / Z scaled by f35 / 36 ... (checked by laying the scan on the photos:
check_cams.py). A head picture for the pipeline = the photo UNDISTORTED and re-projected by a pure rotation about the
camera's centre so the head sits on the optical axis: an exact pinhole picture with its principal point at the centre
(what our camera dict can express), at the camera's true position."""
import re
from pathlib import Path
import numpy as np
import gt


def photo_dir(pose):
    return gt.ROOT / f"hsrd100/x/{pose}/photos"


def cams(pose) -> dict:
    out = {}
    for x in sorted(photo_dir(pose).glob("*.xmp")):
        t = x.read_text()
        a = lambda k: float(re.search(rf'xcr:{k}="([^"]+)"', t).group(1))
        R = np.array(re.search(r"<xcr:Rotation>([^<]+)<", t).group(1).split(), float).reshape(3, 3)
        C = np.array((re.search(r"<xcr:Position>([^<]+)<", t) or re.search(r'xcr:Position="([^"]+)"', t)).group(1).split(), float)
        k = np.array(re.search(r"<xcr:DistortionCoeficients>([^<]+)<", t).group(1).split(), float)[:3]
        name = x.stem.split("_")[-1]
        img = next((p for p in (x.with_suffix(".jpg"), x.with_suffix(".JPG")) if p.exists()), None)
        out[name] = {"R": R, "C": C, "f35": a("FocalLength35mm"), "ppu": a("PrincipalPointU"), "ppv": a("PrincipalPointV"), "k": k, "image": img,
                     "model": re.search(r'xcr:DistortionModel="([^"]+)"', t).group(1)}
    return out


def mask_path(image):
    """The dataset's foreground mask of a photo: <name>.mask.png or <name>.<ext>.mask.png (both namings occur)."""
    for p in (image.with_suffix(".mask.png"), image.with_name(image.name + ".mask.png")):
        if p.exists():
            return p
    return None


def project(cam, X, size, distort=True):
    """Scan-frame points -> photo pixels (w, h = size)."""
    w, h = size
    m = max(w, h)
    Xc = (np.asarray(X, float) - cam["C"]) @ cam["R"].T
    x = Xc[:, :2] / Xc[:, 2:3]
    if distort:
        r2 = (x ** 2).sum(1, keepdims=True)
        x = x * (1 + cam["k"][0] * r2 + cam["k"][1] * r2 ** 2 + cam["k"][2] * r2 ** 3)
    f = cam["f35"] / 36.0 * m
    return np.c_[f * x[:, 0] + w / 2 + cam["ppu"] * m, f * x[:, 1] + h / 2 + cam["ppv"] * m], Xc[:, 2]


def head_view(cam, size, target, out_size=(1152, 1536), px_per_m=3500.0, up=None):
    """The virtual pinhole camera at cam's centre looking AT target (scan frame), `up` kept as the photo's: its rotation
    Rv (world -> camera), focal f (px) so the head is drawn at px_per_m, and a sampler (u, v of the out picture ->
    photo pixels, through the distortion)."""
    z = target - cam["C"]
    dist = float(np.linalg.norm(z))
    z = z / dist
    x = cam["R"][0] - (cam["R"][0] @ z) * z          # the photo's own x axis, made perpendicular: no roll added
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    if up is not None:          # the picture UPRIGHT for this vertical (some rig cameras are mounted on their side)
        y = -(np.asarray(up, float) - (np.asarray(up, float) @ z) * z)
        y /= np.linalg.norm(y)
        x = np.cross(y, z)
    Rv = np.stack([x, y, z])
    f = px_per_m * dist
    w, h = out_size
    uu, vv = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
    rays = np.stack([(uu - w / 2) / f, (vv - h / 2) / f, np.ones_like(uu)], -1) @ Rv         # world directions
    rc = rays @ cam["R"].T
    xn = rc[..., :2] / rc[..., 2:3]
    r2 = (xn ** 2).sum(-1, keepdims=True)
    xd = xn * (1 + cam["k"][0] * r2 + cam["k"][1] * r2 ** 2 + cam["k"][2] * r2 ** 3)
    W, H = size
    m = max(W, H)
    fp = cam["f35"] / 36.0 * m
    return {"R": Rv, "C": cam["C"], "f": f, "size": [w, h], "dist": dist, "map": np.stack([fp * xd[..., 0] + W / 2 + cam["ppu"] * m, fp * xd[..., 1] + H / 2 + cam["ppv"] * m], -1),
            "native_px_per_m": fp / dist}


def resample(img, mp):
    """Bilinear lookup of a (h, w, 3) uint8 picture at pixel positions mp (..., 2) (pixel centres at +0.5)."""
    a = np.asarray(img, np.float32)
    H, W = a.shape[:2]
    u = np.clip(mp[..., 0] - 0.5, 0, W - 1.001)
    v = np.clip(mp[..., 1] - 0.5, 0, H - 1.001)
    x0, y0 = u.astype(int), v.astype(int)
    fx, fy = (u - x0)[..., None], (v - y0)[..., None]
    out = a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x0 + 1] * fx * (1 - fy) + a[y0 + 1, x0] * (1 - fx) * fy + a[y0 + 1, x0 + 1] * fx * fy
    inside = (mp[..., 0] >= 0) & (mp[..., 0] < W) & (mp[..., 1] >= 0) & (mp[..., 1] < H)
    out[~inside] = 0
    return out.astype(np.uint8), inside


def pipeline_cam(view, S_scan_to_world):
    """The pipeline's camera dict for a head_view, in the world the similarity S carries the scan to (GNM world or a
    model's world): Xc = (X - centre) R^T + t with R = _rotvec(r) _CAM0 (yaw 0)."""
    from scipy.spatial.transform import Rotation
    from hifipushie import humanfit
    s, Rs, ts = S_scan_to_world
    Rw = view["R"] @ np.asarray(Rs).T               # world -> camera
    Cw = s * np.asarray(Rs) @ view["C"] + ts
    r = Rotation.from_matrix(Rw @ humanfit._CAM0.T).as_rotvec()
    return {"r": [float(x) for x in r], "t": [float(x) for x in (-Rw @ Cw)], "f": float(view["f"]), "size": list(view["size"]), "centre": [0.0, 0.0, 0.0], "yaw": 0.0}
