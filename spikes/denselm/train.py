"""train.py <out dir> <data root> [epochs=60] [bs=128] [lr=1e-3] [arch=18|34|hm18|hm34] [val=0.08] [workers=8] [limit=N samples]
[seed=0] [train_n=N]: train the denselm network on the dressings under <data root> (each a gen.py output folder).

Pure torch + numpy + PIL (no torchvision, no pretrained weights). Dressings are held out WHOLE for validation (the
last `val` share: a person's skin never on both sides). The training-time augmentation is where the pictures get
their backgrounds and their damage (gen.py renders clean heads on a transparent ground):
  crop        the face box (1.5 x the 68 standard landmarks' extent) x U(0.8, 1.35), shifted +-12 %, turned +-25 deg,
              mirrored half the time (the landmark set's mirror permutation)
  background  plain colours, gradients, soft blobs, hard rectangles and lines, noise
  clothes     the bare bust below a neckline recoloured as cloth on 70 % (the stage is bare skin)
  colour      brightness, contrast, gamma, saturation, hue, grey on 10 %
  damage      downscale to 48-256 px and back, blur, sensor noise, JPEG 25-95, a painterly filter on 12 %
Loss: Wood et al. 2022's Gaussian NLL over (x, y, log sigma) per landmark (beta=0), by default as beta-NLL (beta=0.5).
Writes model.pt (TorchScript, CPU, takes 0..1 RGB NCHW at 256), weights.pth, log.json, val.npz (predictions on the
held-out dressings: clean crops)."""
import io
import json
import math
import os
import sys
import time
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).parent))
import net as netmod  # noqa: E402

SIZE = 256
MEAN = np.array([0.485, 0.456, 0.406], np.float32)
STD = np.array([0.229, 0.224, 0.225], np.float32)


# ---- data -------------------------------------------------------------------------------------------------------------

def pack(root: Path, out: Path, limit: int | None = None) -> dict:
    """Every dressing's pictures in one uint8 memmap (N, S, S, 4) + labels; cached in out."""
    dirs = sorted(d for d in root.iterdir() if (d / "labels.npz").exists() and (d / "meta.npz").exists())
    info = out / "pack.json"
    if info.exists() and json.loads(info.read_text())["dirs"] == [d.name for d in dirs] and json.loads(info.read_text()).get("limit") == limit:
        j = json.loads(info.read_text())
    else:
        xs, vs, dr, side, files = [], [], [], [], []
        size = None
        for k, d in enumerate(dirs):
            lab = np.load(d / "labels.npz")
            meta = np.load(d / "meta.npz")
            size = int(lab["size"])
            fs = sorted(f for f in list(d.glob("[0-9]*.png")) + list(d.glob("[0-9]*.jpg")) if not f.stem.endswith("_a"))
            n = min(len(fs), len(lab["xy"]))
            xs.append(lab["xy"][:n])
            vs.append(lab["vis"][:n])
            dr += [k] * n
            side.append(meta["side"][:n])
            files += fs[:n]
        if limit:
            files = files[:limit]
        N = len(files)
        mm = np.lib.format.open_memmap(out / "pack_img.npy", "w+", np.uint8, (N, size, size, 4))
        for i, f in enumerate(files):
            if f.suffix == ".jpg":          # the slim form (slim.py): RGB as JPEG + the alpha beside it
                rgb = Image.open(f).convert("RGB")
                rgb.putalpha(Image.open(f.with_name(f.stem + "_a.png")).convert("L"))
                mm[i] = np.asarray(rgb)
            else:
                mm[i] = np.asarray(Image.open(f).convert("RGBA"))
        mm.flush()
        del mm
        np.savez(out / "pack_lab.npz", xy=np.concatenate(xs)[:N], vis=np.concatenate(vs)[:N], dressing=np.array(dr)[:N],
                 side=np.concatenate(side)[:N])
        j = {"dirs": [d.name for d in dirs], "n": N, "size": size, "limit": limit}
        info.write_text(json.dumps(j))
    lab = np.load(out / "pack_lab.npz")
    return {"img": np.load(out / "pack_img.npy", mmap_mode="r"), **{k: lab[k] for k in lab.files}, **j}


def background(rng, n=SIZE):
    k = rng.integers(0, 6)
    c0, c1 = rng.uniform(0, 255, 3), rng.uniform(0, 255, 3)
    if rng.random() < 0.5:                       # mostly unsaturated
        c0, c1 = np.full(3, c0.mean()) + rng.normal(0, 12, 3), np.full(3, c1.mean()) + rng.normal(0, 12, 3)
    if k == 0:
        a = np.broadcast_to(c0, (n, n, 3)).copy()
    elif k == 1:
        t = np.linspace(0, 1, n)[:, None, None] if rng.random() < 0.6 else np.linspace(0, 1, n)[None, :, None]
        a = c0 * (1 - t) + c1 * t + np.zeros((n, n, 3))
    elif k in (2, 3):
        m = int(rng.integers(3, 14))
        small = Image.fromarray(rng.uniform(0, 255, (m, m, 3)).astype(np.uint8))
        a = np.asarray(small.resize((n, n), Image.BICUBIC), np.float32)
        a = a * 0.6 + c0 * 0.4
    else:
        im = Image.new("RGB", (n, n), tuple(int(v) for v in c0))
        d = ImageDraw.Draw(im)
        for _ in range(int(rng.integers(3, 14))):
            x0, y0 = rng.uniform(-0.2, 1.0, 2) * n
            w, h = rng.uniform(0.05, 0.8, 2) * n
            col = tuple(int(v) for v in np.clip(c1 + rng.normal(0, 60, 3), 0, 255))
            if rng.random() < 0.7:
                d.rectangle((x0, y0, x0 + w, y0 + h), fill=col)
            else:
                d.line((x0, y0, x0 + w, y0 + h), fill=col, width=int(rng.integers(1, 9)))
        if rng.random() < 0.7:
            im = im.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.5, 8))))
        a = np.asarray(im, np.float32)
    if rng.random() < 0.4:
        a = a + rng.normal(0, rng.uniform(2, 14), a.shape)
    return np.clip(a, 0, 255).astype(np.float32)


def clothe(rng, rgba, xy, lm68):
    """The bare bust below a neckline recoloured as cloth (the picture's own shading kept)."""
    chin, nas = xy[lm68[8]], xy[lm68[27]]
    fh = max(float(np.linalg.norm(chin - nas)), 8.0)
    n = rgba.shape[0]
    xx = np.arange(n)[None, :]
    yy = np.arange(n)[:, None]
    drop = rng.uniform(0.45, 1.0) * fh
    v = rng.uniform(0.0, 0.9) * fh
    wide = rng.uniform(0.35, 1.2) * fh
    line = chin[1] + drop + v * np.clip(1 - np.abs(xx - chin[0]) / wide, 0, 1) if rng.random() < 0.5 else \
        chin[1] + drop + v * np.clip(1 - ((xx - chin[0]) / wide) ** 2, 0, 1)
    m = np.clip((yy - line) / 1.5, 0, 1)[..., None]
    col = rng.uniform(0, 255, 3)
    if rng.random() < 0.4:
        col = np.full(3, rng.uniform(0, 255))
    lum = rgba[..., :3].mean(-1, keepdims=True)
    lum = lum / max(float(np.median(lum[rgba[..., 3] > 128])) if (rgba[..., 3] > 128).any() else 128.0, 1.0)
    cloth = np.clip(col * (0.35 + 0.65 * lum), 0, 255)
    if rng.random() < 0.3:
        per = rng.uniform(3, 14)
        cloth = cloth * (0.8 + 0.2 * np.sign(np.sin((xx * rng.uniform(-1, 1) + yy) * 2 * np.pi / per)))[..., None]
    out = rgba.copy()
    out[..., :3] = rgba[..., :3] * (1 - m) + cloth * m
    return out


def painterly(rng, im):
    k = int(rng.choice([3, 5, 7]))
    im = im.filter(ImageFilter.ModeFilter(k)) if rng.random() < 0.5 else im.filter(ImageFilter.MedianFilter(k))
    a = np.asarray(im, np.float32)
    q = float(rng.uniform(8, 28))
    a = np.round(a / q) * q
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if rng.random() < 0.5:
        im = im.filter(ImageFilter.SMOOTH)
    return im


def damage(rng, im):
    """im: PIL RGB at SIZE."""
    if rng.random() < 0.12:
        im = painterly(rng, im)
    if rng.random() < 0.5:
        s = int(np.exp(rng.uniform(np.log(48), np.log(SIZE))))
        im = im.resize((s, s), Image.BILINEAR if rng.random() < 0.5 else Image.BOX).resize((SIZE, SIZE), Image.BICUBIC if rng.random() < 0.7 else Image.BILINEAR)
    if rng.random() < 0.3:
        im = im.filter(ImageFilter.GaussianBlur(float(rng.uniform(0.3, 2.2))))
    a = np.asarray(im, np.float32)
    # colour
    a = a * rng.uniform(0.6, 1.35) + rng.uniform(-25, 25)
    m = a.mean()
    a = (a - m) * rng.uniform(0.65, 1.4) + m
    g = a.mean(-1, keepdims=True)
    a = g + (a - g) * (0.0 if rng.random() < 0.1 else rng.uniform(0.5, 1.4))
    a = a * rng.uniform(0.9, 1.1, 3)
    a = np.clip(a, 0, 255)
    if rng.random() < 0.5:
        a = 255.0 * (a / 255.0) ** rng.uniform(0.6, 1.6)
    if rng.random() < 0.5:
        a = a + rng.normal(0, rng.uniform(1, 14), a.shape if rng.random() < 0.7 else a.shape[:2] + (1,))
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if rng.random() < 0.5:
        b = io.BytesIO()
        im.save(b, "JPEG", quality=int(rng.integers(25, 96)))
        im = Image.open(io.BytesIO(b.getvalue())).convert("RGB")
    return im


def face_box(xy68):
    lo, hi = xy68.min(0), xy68.max(0)
    return (lo + hi) / 2, 1.5 * float(max(hi - lo))


class Data(torch.utils.data.Dataset):
    def __init__(self, P, idx, L, train: bool, seed: int = 0):
        self.P, self.idx, self.train, self.seed = P, idx, train, seed
        self.mirror, self.lm68 = L["mirror"], L["lm68"]
        self.epoch = 0
        self.strength = 1.0        # the augmentation's strength, 0..1 (main ramps it up: see `ramp`)

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, k):
        i = int(self.idx[k])
        rng = np.random.default_rng((self.seed, self.epoch, i) if self.train else (999, i))
        rgba = np.asarray(self.P["img"][i], np.float32)
        xy = self.P["xy"][i].astype(np.float64)
        c, s0 = face_box(xy[self.lm68])
        a_ = float(self.strength)
        if self.train:
            s = s0 * rng.uniform(1.1 - 0.3 * a_, 1.1 + 0.25 * a_)
            c = c + rng.uniform(-0.12, 0.12, 2) * s * a_
            th = np.radians(rng.uniform(-25, 25)) * a_ if rng.random() < 0.7 else 0.0
            flip = rng.random() < 0.5 * min(1.0, 2 * a_)
            if rng.random() < 0.7:
                rgba = clothe(rng, rgba, xy, self.lm68)
        else:
            s, th, flip = s0 * 1.1, 0.0, False
        k_ = s / SIZE
        ct, st = math.cos(th), math.sin(th)
        fx = -1.0 if flip else 1.0
        # output pixel (u, v) -> source: c + R (k (u' - h), k (v - h)), u' = SIZE - 1 - u when flipped
        h = SIZE / 2          # (continuous pixel coordinates on both sides: a pixel spans [i, i + 1], as Blender's labels)
        a, b = k_ * ct * fx, -k_ * st
        d, e = k_ * st * fx, k_ * ct
        cx = c[0] - a * h - b * h
        cy = c[1] - d * h - e * h
        pm = rgba.copy()
        pm[..., :3] *= pm[..., 3:4] / 255.0
        im = Image.fromarray(pm.astype(np.uint8), "RGBA").transform((SIZE, SIZE), Image.AFFINE, (a, b, cx, d, e, cy),
                                                                    Image.BICUBIC)
        fg = np.asarray(im, np.float32)
        al = fg[..., 3:4] / 255.0
        bg = background(rng) if (self.train and rng.random() < 0.3 + 0.7 * a_) else np.full((SIZE, SIZE, 3), 128.0, np.float32)
        img = Image.fromarray(np.clip(fg[..., :3] + bg * (1 - al), 0, 255).astype(np.uint8))
        if self.train and rng.random() < a_:
            img = damage(rng, img)
        x = (np.asarray(img, np.float32) / 255.0 - MEAN) / STD
        # labels: source -> output pixel
        M = np.array([[a, b], [d, e]])
        uv = (xy - np.array([cx, cy])) @ np.linalg.inv(M).T
        vis = self.P["vis"][i]
        if flip:
            uv, vis = uv[self.mirror], vis[self.mirror]
        t = (uv - h) / (SIZE / 2)
        mmpx = float(self.P["side"][i]) * 1000.0 / self.P["size"] * k_
        return torch.from_numpy(x.transpose(2, 0, 1).copy()), torch.from_numpy(t.astype(np.float32)), torch.from_numpy(vis.astype(np.uint8)), mmpx, i


class Wrapped(torch.nn.Module):
    """0..1 RGB in, (L, 3) out: the normalisation inside the exported model."""
    def __init__(self, m):
        super().__init__()
        self.m = m
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1))

    def forward(self, x):
        return self.m((x - self.mean) / self.std).view(x.shape[0], -1, 3)


def evaluate(model, dl, dev, region):
    model.eval()
    E, S, V, MM, I, XY = [], [], [], [], [], []
    with torch.no_grad():
        for x, t, vis, mmpx, i in dl:
            o = model(x.to(dev)).float().view(x.shape[0], -1, 3).cpu()
            E.append((o[..., :2] - t).norm(dim=-1).numpy() * SIZE / 2)
            S.append(torch.exp(o[..., 2]).numpy() * SIZE / 2)
            V.append(vis.numpy())
            MM.append(mmpx.numpy())
            I.append(i.numpy())
            XY.append(o.numpy())
    E, S, V, MM = np.concatenate(E), np.concatenate(S), np.concatenate(V).astype(bool), np.concatenate(MM)
    rep = {"px_visible": float(E[V].mean()), "px_hidden": float(E[~V].mean()) if (~V).any() else None,
           "px_median_visible": float(np.median(E[V])), "mm_visible": float((E * MM[:, None])[V].mean()),
           "mm_median_visible": float(np.median((E * MM[:, None])[V])),
           "calib_visible": float((E[V] ** 2 / (2 * S[V] ** 2)).mean()), "calib_hidden": float((E[~V] ** 2 / (2 * S[~V] ** 2)).mean()) if (~V).any() else None,
           "within_1sigma": float((E < S)[V].mean()), "within_2sigma": float((E < 2 * S)[V].mean()),
           "sigma_px_visible": float(np.median(S[V])), "sigma_px_hidden": float(np.median(S[~V])) if (~V).any() else None, "regions": {}}
    for r in sorted(set(region.tolist())):
        m = (region == r)[None, :] & V
        if m.any():
            rep["regions"][r] = {"px": round(float(E[m].mean()), 3), "mm": round(float((E * MM[:, None])[m].mean()), 3),
                                 "mm_median": round(float(np.median((E * MM[:, None])[m])), 3),
                                 "calib": round(float((E[m] ** 2 / (2 * S[m] ** 2)).mean()), 3), "sigma_px": round(float(np.median(S[m])), 3),
                                 "visible_share": round(float(m.sum() / max((region == r).sum() * len(E), 1)), 3)}
    return rep, {"err_px": E.astype(np.float32), "sigma_px": S.astype(np.float32), "vis": V, "mmpx": MM.astype(np.float32),
                 "index": np.concatenate(I), "out": np.concatenate(XY).astype(np.float32)}


def main():
    out, root = Path(sys.argv[1]), Path(sys.argv[2])
    kw = dict(a.split("=", 1) for a in sys.argv[3:])
    epochs, bs, lr = int(kw.get("epochs", 60)), int(kw.get("bs", 128)), float(kw.get("lr", 1e-3))
    arch, val, workers = kw.get("arch", "18"), float(kw.get("val", 0.08)), int(kw.get("workers", 8))
    beta = float(kw.get("beta", 0.5))
    ramp = float(kw.get("ramp", 0.25))      # the augmentation comes in over this share of the epochs (from scratch, under the
    # full augmentation from step 0, the network sat at the mean face for hundreds of steps: overfit.py)
    limit, seed = (int(kw["limit"]) if kw.get("limit") else None), int(kw.get("seed", 0))
    out.mkdir(parents=True, exist_ok=True)
    L = json.loads((root / "landmarks.json").read_text()) if (root / "landmarks.json").exists() else None
    if L is None:
        from hifipushie import denselm
        Ld = denselm.landmarks()
        L = {"mirror": Ld["mirror"].tolist(), "lm68": Ld["lm68"].tolist(), "region": Ld["region"].tolist(), "n": int(Ld["n"])}
    L = {"mirror": np.array(L["mirror"]), "lm68": np.array(L["lm68"]), "region": np.array(L["region"]), "n": int(L["n"])}
    (out / "landmarks.json").write_text(json.dumps({k: (v.tolist() if hasattr(v, "tolist") else v) for k, v in L.items()}))
    t0 = time.time()
    P = pack(root, out, limit)
    nd = int(P["dressing"].max()) + 1
    nv = max(1, int(round(val * nd)))
    is_val = P["dressing"] >= nd - nv
    tr, va = np.where(~is_val)[0], np.where(is_val)[0]
    if kw.get("train_n"):                         # a learning-curve point: the first n training samples
        tr = tr[:int(kw["train_n"])]
    print(f"step: packed {P['n']} samples of {nd} dressings in {time.time() - t0:.0f} s; train {len(tr)}, val {len(va)} ({nv} dressings)", flush=True)
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(seed)
    model = netmod.make(arch, L["n"]).to(dev)
    if dev.type == "cuda":
        model = model.to(memory_format=torch.channels_last)
    ds = Data(P, tr, L, True, seed)
    dl = torch.utils.data.DataLoader(ds, bs, shuffle=True, num_workers=workers, drop_last=True, persistent_workers=False, pin_memory=dev.type == "cuda")
    dv = torch.utils.data.DataLoader(Data(P, va, L, False), bs, shuffle=False, num_workers=min(workers, 4))
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    steps = epochs * len(dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, lr, total_steps=steps, pct_start=0.06)
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")
    ema = netmod.make(arch, L["n"]).to(dev)
    ema.load_state_dict(model.state_dict())
    log = []
    for ep in range(epochs):
        ds.epoch = ep
        ds.strength = min(1.0, (ep + 1) / max(ramp * epochs, 1e-9)) if ramp > 0 else 1.0
        model.train()
        t1, tot, nb = time.time(), 0.0, 0
        for x, t, vis, mmpx, i in dl:
            x, t = x.to(dev, non_blocking=True), t.to(dev, non_blocking=True)
            if dev.type == "cuda":
                x = x.to(memory_format=torch.channels_last)
            with torch.autocast(dev.type, enabled=dev.type == "cuda"):
                o = model(x)
            loss = netmod.gnll(o.float(), t, beta=beta)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.unscale_(opt)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(opt)
            scaler.update()
            sched.step()
            with torch.no_grad():
                gstep = ep * len(dl) + nb
                dcy = min(0.998, 1.0 - 25.0 / steps, (1.0 + gstep) / (10.0 + gstep))     # (a short run: a short memory)
                for pe, pm in zip(ema.parameters(), model.parameters()):
                    pe.mul_(dcy).add_(pm.detach(), alpha=1 - dcy)
                for be, bm in zip(ema.buffers(), model.buffers()):
                    be.copy_(bm)
            tot += float(loss)
            nb += 1
        row = {"epoch": ep, "loss": tot / max(nb, 1), "sec": round(time.time() - t1, 1)}
        if ep % max(1, epochs // 12) == 0 or ep == epochs - 1:
            rep, _ = evaluate(ema, dv, dev, L["region"])
            row.update({k: v for k, v in rep.items() if k != "regions"})
        log.append(row)
        print("step: " + json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)
        (out / "log.json").write_text(json.dumps(log))
    rep, pred = evaluate(ema, dv, dev, L["region"])
    (out / "val.json").write_text(json.dumps({**rep, "train_n": int(len(tr)), "val_n": int(len(va)), "epochs": epochs, "arch": arch}, indent=1))
    np.savez_compressed(out / "val.npz", **pred)
    torch.save(ema.state_dict(), out / "weights.pth")
    w = Wrapped(ema).cpu().eval()
    ts = torch.jit.trace(w, torch.zeros(1, 3, SIZE, SIZE))
    ts.save(str(out / "model.pt"))
    print("step: done " + json.dumps({k: v for k, v in rep.items() if k != "regions"}), flush=True)
    print(json.dumps(rep["regions"], indent=1))


if __name__ == "__main__":
    main()
