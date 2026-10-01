#!/usr/bin/env python3
"""Render every report PDF page to PNG for visual QA."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "report" / ".runtime"))

import pypdfium2 as pdfium
from PIL import Image, ImageDraw

PDF = ROOT / "report" / "output" / "Bao_cao_Digital_Twin_Kho_Bao_Quan_Rau_Qua.pdf"
OUT = ROOT / "report" / ".rendered"

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
pdf = pdfium.PdfDocument(str(PDF))
thumbs = []
for index in range(len(pdf)):
    bitmap = pdf[index].render(scale=1.8)
    image = bitmap.to_pil().convert("RGB")
    path = OUT / f"page-{index + 1:03d}.png"
    image.save(path, quality=95)
    thumb = image.copy()
    thumb.thumbnail((260, 370))
    thumbs.append((index + 1, thumb))

cols = 4
rows = (len(thumbs) + cols - 1) // cols
sheet = Image.new("RGB", (cols * 300, rows * 410), "#CBD5E1")
draw = ImageDraw.Draw(sheet)
for i, (number, thumb) in enumerate(thumbs):
    x = (i % cols) * 300 + 20
    y = (i // cols) * 410 + 25
    sheet.paste(thumb, (x, y))
    draw.text((x, y + 375), f"Trang {number}", fill="#111827")
sheet.save(OUT / "contact-sheet.png")
print(f"rendered_pages={len(pdf)}")
