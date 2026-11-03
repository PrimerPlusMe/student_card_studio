"""Generate the original Student Card Studio icon using vector drawing operations."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
assets = root / "assets"
assets.mkdir(exist_ok=True)
size = 1024
image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((20, 20, 1004, 1004), radius=224, fill="#1652b8")
draw.rounded_rectangle((42, 42, 982, 982), radius=204, fill="#1e63d5")
draw.ellipse((590, -120, 1250, 540), fill="#3379e5")
draw.rounded_rectangle((146, 208, 878, 828), radius=72, fill="#103e91")
draw.rounded_rectangle((146, 184, 878, 804), radius=72, fill="#ffffff")
draw.rounded_rectangle((210, 252, 814, 326), radius=20, fill="#e6efff")
draw.rounded_rectangle((210, 374, 450, 648), radius=30, fill="#e6efff")
draw.ellipse((278, 408, 382, 512), fill="#2c68c9")
draw.rounded_rectangle((246, 526, 414, 630), radius=70, fill="#2c68c9")
draw.rounded_rectangle((494, 390, 778, 424), radius=15, fill="#23354e")
draw.rounded_rectangle((494, 464, 722, 490), radius=12, fill="#93a6be")
draw.rounded_rectangle((494, 528, 752, 554), radius=12, fill="#93a6be")
draw.rounded_rectangle((494, 592, 680, 618), radius=12, fill="#93a6be")
x = 236
for i, width in enumerate([8, 16, 8, 8, 24, 8, 16, 8, 8, 24, 16, 8, 16, 24, 8, 8, 16, 8, 24, 8, 8]):
    draw.rectangle((x, 692, x + width, 746), fill="#23354e")
    x += width + (8 if i % 3 else 16)
alpha = Image.new("L", (size, size), 0)
ImageDraw.Draw(alpha).rounded_rectangle((20, 20, 1004, 1004), radius=224, fill=255)
image.putalpha(alpha)
image.save(assets / "app.png")
image.save(assets / "app.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
image.save(assets / "app.icns")
print("Generated assets/app.png, app.ico and app.icns")
