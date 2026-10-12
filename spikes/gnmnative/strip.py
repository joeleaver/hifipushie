"""strip.py <out.png> [tile=480] <label>=<image> ...: images side by side with LARGE labels over each (one row).
sheet.py builds Joe's sheets from rows of these."""
import sys

from PIL import Image, ImageDraw, ImageFont


def font(size):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            pass
    return ImageFont.load_default()


def row(items, T=480, label_h=None, fs=None):
    """items: [(label, path or Image or None)] -> one image."""
    fs = fs or max(18, T // 14)
    label_h = label_h or int(fs * 1.6)
    W = Image.new("RGB", (T * len(items), T + label_h), "white")
    d = ImageDraw.Draw(W)
    f = font(fs)
    for k, (lab, im) in enumerate(items):
        if im is not None:
            im = Image.open(im) if isinstance(im, str) else im
            W.paste(im.convert("RGB").resize((T, T), Image.LANCZOS), (k * T, label_h))
        else:
            d.rectangle([k * T, label_h, (k + 1) * T, T + label_h], fill=(225, 225, 225))
            d.text((k * T + T // 2 - fs * 3, label_h + T // 2), "(no picture)", fill=(120, 120, 120), font=font(fs // 2 + 6))
        d.text((k * T + 8, 4), lab, fill=(0, 0, 0), font=f)
    return W


def stack(rows, title=None, fs=40):
    w = max(r.width for r in rows)
    th = int(fs * 1.7) if title else 0
    S = Image.new("RGB", (w, sum(r.height for r in rows) + th), "white")
    if title:
        ImageDraw.Draw(S).text((10, 6), title, fill=(0, 0, 0), font=font(fs))
    y = th
    for r in rows:
        S.paste(r, (0, y))
        y += r.height
    return S


if __name__ == "__main__":
    out = sys.argv[1]
    args = sys.argv[2:]
    T = 480
    if args and args[0].startswith("tile="):
        T = int(args.pop(0)[5:])
    row([tuple(a.split("=", 1)) for a in args], T).save(out)
    print(out)
