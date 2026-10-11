import sys

from PIL import Image

im = Image.open(sys.argv[1]).convert("RGB")
print(im.size)
W, H = im.size
out = Image.new("RGB", (W, 2 * 250), (255, 255, 255))
out.paste(im.crop((0, 40, W, 290)), (0, 0))
out.paste(im.crop((0, 284, W, 534)), (0, 250))
out.save(sys.argv[2])
