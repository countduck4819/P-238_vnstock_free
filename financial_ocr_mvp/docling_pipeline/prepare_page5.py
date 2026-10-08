"""Render and crop the difficult page-5 financial table at high resolution."""
from pathlib import Path
import fitz
from PIL import Image

BASE = Path(__file__).resolve().parents[1]
PDF = BASE / "pdf" / "FPT_Q1_2015_consolidated_2316c6e5.pdf"
OUT = BASE / "output" / "docling"
OUT.mkdir(parents=True, exist_ok=True)

with fitz.open(PDF) as document:
    page = document[4]
    pixmap = page.get_pixmap(dpi=400, alpha=False)
    rendered = OUT / "page_005_400dpi.png"
    pixmap.save(rendered)

image = Image.open(rendered).convert("RGB")
# The existing 200-DPI crop is (120,330,2200,1250) after -90 degree rotation.
rotated = image.rotate(-90, expand=True)
scale = 400 / 200
box = tuple(round(value * scale) for value in (120, 330, 2200, 1250))
crop = rotated.crop(box)
crop_path = OUT / "page_005_table_400dpi.png"
crop.save(crop_path)
print("Rendered:", rendered)
print("Cropped:", crop_path)
print("Crop size:", crop.size)
