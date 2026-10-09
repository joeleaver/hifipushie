"""posecal.py train [n] | photo: an expression's POSE (base.POSE words, mm) read from the detector's blendshapes
instead of set by hand. MediaPipe's 52 blendshape scores answer "how far from ITS neutral face", and a face's own
identity leaks into them (a naturally low brow reads browDown), so the map is learnt on our own renders: n sampled
heads (identity sigma 0.8), each with a random pose, a random camera (yaw / pitch +-7 deg, lens 50-85) and light,
skinned or clay; ridge regression blendshapes (+ their squares) -> pose, cross-validated: the cv rms against the
sampled spread says what the scores can tell apart from identity.
  train: $D3/posecal_train.npz, $D3/posecal_model.npz, prints the table
  photo: the model on Garrett's front photo -> $D3/garrett_pose.json {key: [mm, +-mm]}"""
import json
import os
import sys

import numpy as np

import rs

D3 = os.environ.get("D3", "/mnt/data/hifipushie/garrett3")
KEYS = ("smile", "mouth_width", "lid_upper", "lid_lower", "brow_inner", "brow_outer")
SPREAD = {"smile": 0.003, "mouth_width": 0.002, "lid_upper": 0.002, "lid_lower": 0.0012, "brow_inner": 0.003, "brow_outer": 0.0025}


def sample(n, seed=11):
    rng = np.random.default_rng(seed)
    X, Y, names = [], [], None
    imgs, poses = [], []
    for i in range(n):
        c = rng.normal(0, 0.8, rs.K_TRUE)
        pose = {k: float(rng.uniform(-1, 1) * SPREAD[k]) * (rng.uniform() < 0.8) for k in KEYS}
        V = rs.head(c, rs.expression({k: v for k, v in pose.items() if v}) if any(pose.values()) else None)
        cam = rs.make_cam(V, yaw=rng.uniform(-7, 7), pitch=rng.uniform(-7, 7), roll=rng.uniform(-3, 3), lens=rng.uniform(50, 85),
                          size=(512, 512))
        light = np.array([rng.uniform(-0.5, 0.5), -1.0, rng.uniform(0.0, 0.8)])
        img, _ = rs.render(V, cam, light=_cam_light(light, cam), albedo=rs.skinned_albedo(int(rng.integers(0, 6))) if i % 2 else None)
        imgs.append(img)
        poses.append([pose[k] for k in KEYS])
        if len(imgs) == 64 or i == n - 1:
            for d, p in zip(rs.detect(imgs), poses):
                if d is None or not d.get("bs"):
                    continue
                names = names or sorted(d["bs"])
                X.append([d["bs"][k] for k in names])
                Y.append(p)
            imgs, poses = [], []
            print(f"  {i + 1} / {n}: {len(X)} detected", flush=True)
    return np.array(X), np.array(Y), names


def _cam_light(world_dir, cam):
    """rs.render's light is in the camera's frame (as likeness.KEY): the world direction turned into it."""
    from hifipushie import humanfit
    return humanfit._cam_rot(cam) @ (np.asarray(world_dir, float) / np.linalg.norm(world_dir)) * np.array([1, 1, 1.0])


def feats(X):
    return np.c_[X, X ** 2, np.ones(len(X))]


def ridge(F, Y, lam=1e-2):
    mu, sd = F.mean(0), F.std(0) + 1e-6
    Z = (F - mu) / sd
    Z[:, -1] = 1.0
    A = Z.T @ Z + lam * len(Z) * np.eye(Z.shape[1])
    return {"W": np.linalg.solve(A, Z.T @ Y), "mu": mu, "sd": sd}


def predict(M, F):
    Z = (F - M["mu"]) / M["sd"]
    Z[:, -1] = 1.0
    return Z @ M["W"]


def train(n=600):
    f = f"{D3}/posecal_train.npz"
    if os.path.exists(f) and int(np.load(f)["X"].shape[0]) >= 0.8 * n:
        z = np.load(f, allow_pickle=True)
        X, Y, names = z["X"], z["Y"], list(z["names"])
    else:
        X, Y, names = sample(n)
        np.savez(f, X=X, Y=Y, names=np.array(names))
    F = feats(X)
    fold = np.arange(len(F)) % 5
    P = np.zeros_like(Y)
    for k in range(5):
        P[fold == k] = predict(ridge(F[fold != k], Y[fold != k]), F[fold == k])
    rms = np.sqrt(((P - Y) ** 2).mean(0))
    sd = Y.std(0)
    print(f"{len(F)} heads. key: cv rms mm / sampled sd mm (1.0 = the scores say nothing); strongest scores")
    M = ridge(F, Y)
    for j, k in enumerate(KEYS):
        cr = [abs(np.corrcoef(X[:, i], Y[:, j])[0, 1]) if X[:, i].std() > 1e-6 else 0.0 for i in range(X.shape[1])]
        top = np.argsort(cr)[::-1][:3]
        print(f"  {k:12s} {rms[j] * 1000:.2f} / {sd[j] * 1000:.2f} = {rms[j] / sd[j]:.2f}   " + ", ".join(f"{names[i]} r {cr[i]:.2f}" for i in top))
    np.savez(f"{D3}/posecal_model.npz", W=M["W"], mu=M["mu"], sd=M["sd"], rms=rms, names=np.array(names))
    return M, rms, names


def photo():
    import garrett3
    z = np.load(f"{D3}/posecal_model.npz", allow_pickle=True)
    M, rms, names = {"W": z["W"], "mu": z["mu"], "sd": z["sd"]}, z["rms"], list(z["names"])
    _, _, d = garrett3.photo_features(list(range(3)))
    bs = d["bs"]
    print("the photo's strongest scores:", sorted(((round(v, 2), k) for k, v in bs.items() if v > 0.08), reverse=True)[:14])
    p = predict(M, feats(np.array([[bs[k] for k in names]])))[0]
    out = {k: [round(float(p[j]) * 1000, 2), round(float(rms[j]) * 1000, 2)] for j, k in enumerate(KEYS)}
    print("pose read from the photo (mm, +- cv rms):", out)
    json.dump(out, open(f"{D3}/garrett_pose.json", "w"), indent=1)
    return out


if __name__ == "__main__":
    if sys.argv[1] == "train":
        train(int(sys.argv[2]) if len(sys.argv) > 2 else 600)
    else:
        photo()
