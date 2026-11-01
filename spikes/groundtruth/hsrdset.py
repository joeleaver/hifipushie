"""hsrdset.py: loader for the HSRD-100 real-photo set with scan truth (built by hsrd_pull.sh / hsrd_export.py; notes:
docs/notes/groundtruth.md "## The HSRD-100 real-photo set"). The data is NOT in the repo: $HIFIPUSHIE_GROUNDTRUTH/hsrd100
(default /mnt/data/hifipushie/groundtruth/hsrd100). CC BY 4.0: index()["attribution"] must accompany anything shown.

    import hsrdset as H
    idx = H.index()                              # subjects (age, sex), poses, the fixed split, attribution
    for pose in H.poses(split="train"):          # or "heldout" / None
        P = H.Pose(pose)
        for cam in P.photos(az=(-30, 30)):       # camera names by where they stand round the head (degrees)
            img = P.image(cam)                   # PIL, the head-and-shoulders cut at the rig photo's own resolution
            xy, vis, q = P.labels(cam, "dl3")    # (756, 2) px in the cut; visible (ray cast on the scan); fit quality mm
            ok = P.good(cam, "dl3")              # visible AND on measured skin within 1.5 mm: THE labels to use
            K = P.camera(cam)                    # f, cx, cy, k (brown3), R, C (rig frame), az, el, dist_m, px_per_mm, roll_deg
        V, F = P.scan()["V"], P.scan()["F"]      # the scan's head (scan frame; P.to_rig(V) carries it to the rig's)
        c, e = P.fit()["identity_expression"]["c"], P.fit()["identity_expression"]["e"]
    python spikes/groundtruth/hsrdset.py check   # every pose: files present, labels inside their cuts, a count table
    python spikes/groundtruth/hsrdset.py sheet <pose> <out.png>   # labels drawn on six photos (LOOK at them)
Sets: "dl3" (denselm v3: 756 GNM vertices, regions in labels["dl3_region"]), "lm68", "mp" (readmix's MediaPipe ->
GNM points: labels["mp_id"] gives each row's MediaPipe index). project(cam, X_rig) projects any rig-frame points."""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(os.environ.get("HIFIPUSHIE_GROUNDTRUTH", "/mnt/data/hifipushie/groundtruth")) / "hsrd100"


def index() -> dict:
    return json.loads((ROOT / "index.json").read_text())


def poses(split: str | None = None) -> list:
    idx = index()
    return [p for p, d in idx["poses"].items() if split is None or idx["subjects"][d["subject"]]["split"] == split]


class Pose:
    def __init__(self, pose: str):
        self.pose = pose
        self.dir = ROOT / pose.split("-")[0] / pose
        self.cams = json.loads((self.dir / "cameras.json").read_text())
        self._lab = None

    def photos(self, az=None, el=None, min_px_per_mm: float = 0.0) -> list:
        out = []
        for n, c in self.cams["cameras"].items():
            if az is not None and not (az[0] <= c["az"] <= az[1]):
                continue
            if el is not None and not (el[0] <= c["el"] <= el[1]):
                continue
            if c["px_per_mm"] < min_px_per_mm:
                continue
            out.append(n)
        return out

    def camera(self, cam: str) -> dict:
        return self.cams["cameras"][cam]

    def image(self, cam: str):
        from PIL import Image
        return Image.open(self.dir / self.cams["cameras"][cam]["file"]).convert("RGB")

    def mask(self, cam: str):
        from PIL import Image
        m = self.cams["cameras"][cam].get("mask")
        return None if not m else Image.open(self.dir / m).convert("L")

    @property
    def lab(self):
        if self._lab is None:
            z = np.load(self.dir / "labels.npz")
            self._lab = {k: z[k] for k in z.files}
        return self._lab

    def labels(self, cam: str, which: str = "dl3"):
        """(xy (n, 2) px in the cut, visible (n,) bool, quality (n,) mm: the fit's distance to the scan there, nan = no
        skin under the label). lab[f"{which}_form"]: vermilion-border labels (form only, not the colour edge)."""
        i = list(self.lab["photos"]).index(cam)
        return self.lab[f"{which}_xy"][i], self.lab[f"{which}_vis"][i], self.lab[f"{which}_q"]

    def good(self, cam: str, which: str = "dl3", max_q: float = 1.5, form: bool = True) -> np.ndarray:
        """The labels worth using in that photo: visible AND measured (the fit lies within max_q mm of the scan's SKIN
        there). `vis` alone is geometric: where the fit has no skin under it (q nan: scalp under hair, a hat) the GNM
        surface is the prior's guess and may even stand outside the hair: never use those. form=False also drops the
        vermilion-border labels (form only, not the colour edge)."""
        xy, vis, q = self.labels(cam, which)
        ok = vis & np.isfinite(q) & (np.nan_to_num(q, nan=1e9) <= max_q)
        return ok if form else ok & ~self.lab[f"{which}_form"]

    def project(self, cam: str, X) -> np.ndarray:
        """rig-frame points -> pixels in the cut (through the distortion)."""
        c = self.cams["cameras"][cam]
        Xc = (np.asarray(X, float) - np.asarray(c["C"])) @ np.asarray(c["R"]).T
        x = Xc[:, :2] / Xc[:, 2:3]
        r2 = (x ** 2).sum(1, keepdims=True)
        k = c["k"]
        x = x * (1 + k[0] * r2 + k[1] * r2 ** 2 + k[2] * r2 ** 3)
        return np.c_[c["f"] * x[:, 0] + c["cx"], c["f"] * x[:, 1] + c["cy"]]

    def to_rig(self, X) -> np.ndarray:
        T = self.cams["T_scan_to_rig"]
        return np.asarray(X, float) @ np.asarray(T["R"]).T + np.asarray(T["t"])

    def scan(self, decimated: bool = False) -> dict:
        z = np.load(self.dir / ("scan_head_dec.npz" if decimated else "scan_head.npz"))
        return {k: z[k] for k in z.files}

    def texture(self):
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        return Image.open(self.dir / "scan_head_texture.png")

    def fit(self) -> dict:
        return json.loads((self.dir / "fit.json").read_text())

    def summary(self) -> dict:
        return json.loads((self.dir / "summary.json").read_text())


def sheet(pose: str, out: str, which: str = "dl3", n: int = 6):
    from PIL import Image, ImageDraw
    P = Pose(pose)
    names = sorted(P.cams["cameras"], key=lambda c: P.camera(c)["az"])
    pick = [names[int(round(i))] for i in np.linspace(0, len(names) - 1, n)]
    tiles = []
    for c in pick:
        im = P.image(c)
        xy, vis, q = P.labels(c, which)
        d = ImageDraw.Draw(im)
        r = max(2, im.width // 400)
        for (x, y), v, qq in zip(xy, vis, q):
            if not v:
                continue
            col = (0, 255, 0) if np.isfinite(qq) and qq < 1.0 else (255, 200, 0) if np.isfinite(qq) else (255, 0, 255)
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)
        k = 700 / im.height
        im = im.resize((int(im.width * k), 700))
        ImageDraw.Draw(im).text((8, 8), f"{c} az {P.camera(c)['az']:+.0f} el {P.camera(c)['el']:+.0f} {150 * P.camera(c)['px_per_mm']:.0f} px face; visible {int(vis.sum())}", fill=(255, 255, 0))
        tiles.append(im)
    s = Image.new("RGB", (sum(t.width for t in tiles), 700))
    x = 0
    for t in tiles:
        s.paste(t, (x, 0))
        x += t.width
    s.save(out)


def check() -> dict:
    tot = {"poses": 0, "photos": 0, "bins": {"front": 0, "three-quarter": 0, "profile": 0, "rear": 0}, "bytes": 0}
    for p in poses():
        P = Pose(p)
        s = P.summary()
        assert len(P.lab["photos"]) == len(P.cams["cameras"]) == s["photos"], p
        for c in list(P.cams["cameras"])[:3]:
            assert (P.dir / P.camera(c)["file"]).exists(), (p, c)
            xy, vis, q = P.labels(c)
            w, h = P.camera(c)["size"]
            assert ((xy[vis] >= 0) & (xy[vis] < [w, h])).all(), (p, c)
            assert np.abs(P.project(c, P.lab["dl3_X"]) - xy).max() < 0.05, (p, c)
        tot["poses"] += 1
        tot["photos"] += s["photos"]
        tot["bytes"] += s["bytes"]
        for k in tot["bins"]:
            tot["bins"][k] += s["bins"][k]
        print(f"{p}: {s['photos']} photos {s['bins']}; face {s['face_px']:.0f} px (median); fit {s['fit_face_mean_mm']:.2f} / {s['fit_face_p90_mm']:.2f} mm{' FLAG' if s['flag'] else ''}; {s['bytes'] / 1e6:.0f} MB")
    print(tot)
    return tot


if __name__ == "__main__":
    import sys
    if sys.argv[1] == "check":
        check()
    elif sys.argv[1] == "sheet":
        sheet(sys.argv[2], sys.argv[3], *(sys.argv[4:5]))
