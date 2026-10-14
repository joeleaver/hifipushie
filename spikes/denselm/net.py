"""The denselm network: a plain ResNet (BasicBlock, 18 / 34 layers; our own few lines, no torchvision, no pretrained
weights: trained from scratch on our synthetic renders only) regressing, from a 256 px face crop, 3 numbers per
landmark: x, y in [-1, 1] over the crop and log sigma (Wood et al. 2022: direct regression + a Gaussian negative log
likelihood, so each landmark carries its own uncertainty)."""
import torch
import torch.nn as nn
import torch.nn.functional as F


class Block(nn.Module):
    def __init__(self, cin, cout, stride):
        super().__init__()
        self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
        self.b1 = nn.BatchNorm2d(cout)
        self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
        self.b2 = nn.BatchNorm2d(cout)
        self.sc = None
        if stride != 1 or cin != cout:
            self.sc = nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

    def forward(self, x):
        y = F.relu(self.b1(self.c1(x)))
        y = self.b2(self.c2(y))
        return F.relu(y + (x if self.sc is None else self.sc(x)))


class Net(nn.Module):
    def __init__(self, n_landmarks: int, layers=(2, 2, 2, 2), width: int = 64):
        super().__init__()
        self.n = n_landmarks
        self.stem = nn.Sequential(nn.Conv2d(3, width, 7, 2, 3, bias=False), nn.BatchNorm2d(width), nn.ReLU(inplace=True),
                                  nn.MaxPool2d(3, 2, 1))
        blocks, cin = [], width
        for i, k in enumerate(layers):
            cout = width * 2 ** i
            for j in range(k):
                blocks.append(Block(cin, cout, 2 if (j == 0 and i > 0) else 1))
                cin = cout
        self.body = nn.Sequential(*blocks)
        self.head = nn.Linear(cin, n_landmarks * 3)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)
        with torch.no_grad():
            self.head.bias.view(n_landmarks, 3)[:, 2] = -2.0          # start at sigma ~ 0.14 (of the half crop)

    def forward(self, x):
        y = self.body(self.stem(x))
        return self.head(torch.flatten(F.adaptive_avg_pool2d(y, 1), 1))


class NetHM(nn.Module):
    """The same backbone, a more sample-efficient head (integral regression, Sun et al. 2018): per landmark a 32 x 32
    heat map from a small feature pyramid, its soft-argmax as the position, PLUS a global offset and log sigma from
    the pooled features (so a landmark can lie outside the crop, and hidden ones get their own uncertainty). The
    output and the loss are the same as Net's: (x, y, log sigma) per landmark, Gaussian NLL. For SMALL training sets
    (the pilot): the direct regressor has to learn where things are from scratch through one pooled vector."""
    def __init__(self, n_landmarks: int, layers=(2, 2, 2, 2), width: int = 64, grid: int = 32, extra: int = 0):
        super().__init__()
        self.n = n_landmarks
        self.stem = nn.Sequential(nn.Conv2d(3, width, 7, 2, 3, bias=False), nn.BatchNorm2d(width), nn.ReLU(inplace=True),
                                  nn.MaxPool2d(3, 2, 1))
        stages, cin = [], width
        for i, k in enumerate(layers):
            cout = width * 2 ** i
            stages.append(nn.Sequential(*[Block(cin if j == 0 else cout, cout, 2 if (j == 0 and i > 0) else 1) for j in range(k)]))
            cin = cout
        self.stages = nn.ModuleList(stages)
        d = 192
        self.lat = nn.ModuleList([nn.Conv2d(width * 2 ** i, d, 1) for i in (1, 2, 3)])
        self.smooth = nn.Sequential(nn.Conv2d(d, d, 3, 1, 1, bias=False), nn.BatchNorm2d(d), nn.ReLU(inplace=True))
        self.maps = nn.Conv2d(d, n_landmarks, 1)
        self.extra = extra          # rows after the landmarks that have no heat map (the camera's distance): from the pooled features alone
        self.head = nn.Linear(cin, (n_landmarks + extra) * 3)
        nn.init.zeros_(self.head.weight)
        nn.init.zeros_(self.head.bias)
        with torch.no_grad():
            self.head.bias.view(n_landmarks + extra, 3)[:, 2] = -2.0
        g = (torch.arange(grid, dtype=torch.float32) + 0.5) / grid * 2 - 1
        self.register_buffer("gx", g.view(1, 1, 1, grid).repeat(1, 1, grid, 1).reshape(1, 1, -1))
        self.register_buffer("gy", g.view(1, 1, grid, 1).repeat(1, 1, 1, grid).reshape(1, 1, -1))
        self.temp = nn.Parameter(torch.tensor(1.0))

    def forward(self, x):
        y = self.stem(x)
        c = []
        for s in self.stages:
            y = s(y)
            c.append(y)
        p = self.lat[2](c[3])
        p = self.lat[1](c[2]) + F.interpolate(p, scale_factor=2.0, mode="nearest")
        p = self.lat[0](c[1]) + F.interpolate(p, scale_factor=2.0, mode="nearest")
        h = self.maps(self.smooth(p)).float()
        w = torch.softmax(h.flatten(2) * self.temp, dim=2)
        sx, sy = (w * self.gx).sum(2), (w * self.gy).sum(2)
        o = self.head(torch.flatten(F.adaptive_avg_pool2d(c[3], 1), 1)).float().view(x.shape[0], self.n + self.extra, 3)
        lm = torch.stack([sx + o[:, :self.n, 0], sy + o[:, :self.n, 1], soft_floor(o[:, :self.n, 2])], dim=2)
        ex = torch.stack([o[:, self.n:, 0], o[:, self.n:, 1], soft_floor(o[:, self.n:, 2])], dim=2)
        return torch.cat([lm, ex], dim=1).flatten(1)


LS_MIN = -5.5         # sigma >= ~0.5 px of the 256 crop (coordinates in [-1, 1])


def soft_floor(ls):
    """log sigma with a SOFT floor: sigma^2 = exp(2 ls) + exp(2 LS_MIN). The earlier hard clamp in the loss had zero
    gradient below the floor: a landmark whose sigma went under it could not raise it again, and its d^2 / sigma^2 term
    (thousands on a hard sample) blew the stage-1 runs up (s10k; s30k's first try: loss 0.9 -> 148 at epoch 9). In the
    network, so the loss, the evaluation and the exported model all see the same sigma."""
    return 0.5 * torch.logaddexp(2 * ls, torch.full_like(ls, 2 * LS_MIN))


def make(arch: str, n_landmarks: int, extra: int = 0):
    """arch: "18" | "34" (direct regression, Wood et al.) | "hm18" | "hm34" (the heat-map head)."""
    layers = (3, 4, 6, 3) if arch.endswith("34") else (2, 2, 2, 2)
    return NetHM(n_landmarks, layers, extra=extra) if arch.startswith("hm") else Net(n_landmarks + extra, layers)


def gnll(out, xy, weight=None, beta: float = 0.0):
    """Wood et al. 2022's loss: sum_i [ log sigma_i^2 + |mu_i - x_i|^2 / (2 sigma_i^2) ] (x, y in [-1, 1]).
    beta > 0: the beta-NLL of Seitzer et al. 2022: each landmark's term x its own (detached) sigma^(2 beta), so a
    landmark the network is unsure of still pulls on its position (the plain NLL's pull falls with 1 / sigma^2: the
    mean fit stalls early); the optimum, and so the calibration, is the same."""
    o = out.view(out.shape[0], -1, 3)
    ls = o[..., 2].clamp(max=3.0)        # the floor is soft_floor's, in the network (NetHM); a hard clamp here had no gradient
    d2 = ((o[..., :2] - xy) ** 2).sum(-1)
    l = 2 * ls + d2 / (2 * torch.exp(2 * ls))
    if beta > 0:
        l = l * torch.exp(2 * beta * ls).detach()
    if weight is not None:
        l = l * weight
    return l.mean()
