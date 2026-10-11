"""GNM's semantic samplers (google/GNM gnm/shape/semantic_sampler.py, Apache 2.0) without TensorFlow: the two Keras
CVAE decoders' weights (gnm_sampler.npz, dumped from the asset pack's .h5 files) run in numpy, with exact Jacobians.

identity():   z (64) + label (6: female, male | middle_eastern, asian, white, black) -> 253 identity coefficients
expression(): z (64) + label (20 classes, EXPR)                                      -> 383 expression coefficients
Google trains them on 12K samples with mixup on the labels (convex blends of two classes), so a label is a continuous
control inside the simplex (sex t in [0, 1], ethnicity weights summing to 1); outside it is extrapolation.
What the study found (docs/notes/gnm_atlas.md "## gnmcontrols"): the identity decoder's samples sit |c| ~5.5 off
GNM's template (its training set's mean is not GNM's), use ~36 of 64 latent dims, and span ~65 directions for 90 % of
their variance: a 64-d latent can't represent GNM's N(0, I) heads or our fitted people (residual > |c|), so it is a
plausible-face GENERATOR and a source of labelled directions (sex, ethnicity), not a fitting space. The expression
decoder uses ~5 latent dims per class: its class prototypes (z = 0) are the useful part (data-backed whole-face
expressions: eyes + mouth together)."""
from __future__ import annotations

from pathlib import Path

import numpy as np

DATA = Path(__file__).with_name("gnm_sampler.npz")
GENDER = ["female", "male"]
ETH = ["middle_eastern", "asian", "white", "black"]
EXPR = ["surprise", "disgust", "suck", "compress_face", "stretch_face", "happy", "squint", "platysma", "blow",
        "funneler", "smile_wide", "corners_down", "pucker", "wink_left", "wink_right", "mouth_left", "mouth_right",
        "lips_roll_in", "snarl", "tongue_center"]
_C: dict = {}


class Decoder:
    """A Keras Dense-ReLU stack on concat(z, label), linear last layer."""

    def __init__(self, tag: str):
        z = np.load(DATA)
        self.W, self.b = [], []
        k = 0
        while f"{tag}_W{k}" in z.files:
            self.W.append(z[f"{tag}_W{k}"].astype(np.float64))
            self.b.append(z[f"{tag}_b{k}"].astype(np.float64))
            k += 1
        self.nz = 64
        self.nl = self.W[0].shape[0] - 64
        self.nout = self.W[-1].shape[1]

    def __call__(self, zz, lab) -> np.ndarray:
        zz, lab = np.atleast_2d(np.asarray(zz, float)), np.atleast_2d(np.asarray(lab, float))
        if len(lab) == 1 and len(zz) > 1:
            lab = np.repeat(lab, len(zz), 0)
        if len(zz) == 1 and len(lab) > 1:
            zz = np.repeat(zz, len(lab), 0)
        x = np.concatenate([zz, lab], 1)
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            x = x @ W + b
            if i < len(self.W) - 1:
                x = np.maximum(x, 0)
        return x

    def jac(self, z1, lab1) -> np.ndarray:
        """d out / d [z, label] at one point: (nout, 64 + nl)."""
        x = np.concatenate([np.asarray(z1, float).ravel(), np.asarray(lab1, float).ravel()])
        J = np.eye(len(x))
        for i, (W, b) in enumerate(zip(self.W, self.b)):
            x = x @ W + b
            J = J @ W
            if i < len(self.W) - 1:
                m = x > 0
                x = np.maximum(x, 0)
                J = J * m[None, :]
        return J.T


def identity() -> Decoder:
    if "id" not in _C:
        _C["id"] = Decoder("id")
    return _C["id"]


def expression() -> Decoder:
    if "ex" not in _C:
        _C["ex"] = Decoder("ex")
    return _C["ex"]


def id_label(sex, eth=None) -> np.ndarray:
    """sex: "female" | "male" | t (0 female .. 1 male) | {name: w}; eth: a name | {name: w} | None (uniform)."""
    c = np.zeros(6)
    if isinstance(sex, (int, float)):
        c[0], c[1] = 1 - float(sex), float(sex)
    elif isinstance(sex, dict):
        for k, w in sex.items():
            c[GENDER.index(k)] += w
    else:
        c[GENDER.index(sex)] = 1
    if eth is None:
        c[2:] = 0.25
    elif isinstance(eth, dict):
        for k, w in eth.items():
            c[2 + ETH.index(k)] += w
    else:
        c[2 + ETH.index(eth)] = 1
    return c


def ex_label(cls, w: float = 1.0) -> np.ndarray:
    c = np.zeros(len(EXPR))
    if isinstance(cls, dict):
        for k, v in cls.items():
            c[EXPR.index(k)] += v
    else:
        c[EXPR.index(cls)] = w
    return c


def prototype(cls) -> np.ndarray:
    """An expression class's prototype (decoded at z = 0; 383 coefficients). A blend: {class: weight}, normalised."""
    if isinstance(cls, dict):
        s = sum(cls.values())
        cls = {k: v / s for k, v in cls.items()}
    return expression()(np.zeros(64), ex_label(cls))[0]
