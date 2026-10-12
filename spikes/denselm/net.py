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


def gnll(out, xy, weight=None):
    """Wood et al. 2022's loss: sum_i [ log sigma_i^2 + |mu_i - x_i|^2 / (2 sigma_i^2) ] (x, y in [-1, 1])."""
    o = out.view(out.shape[0], -1, 3)
    ls = o[..., 2].clamp(-7.0, 3.0)
    d2 = ((o[..., :2] - xy) ** 2).sum(-1)
    l = 2 * ls + d2 / (2 * torch.exp(2 * ls))
    if weight is not None:
        l = l * weight
    return l.mean()
