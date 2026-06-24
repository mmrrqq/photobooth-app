from pathlib import Path
from typing import Self

import numpy as np
from numpy import typing as npt
from PIL import Image, ImageDraw, ImageFont


def _draw_dashed_line(draw: ImageDraw.ImageDraw, y: int, x0: int, x1: int, dash: int = 8, gap: int = 6, fill: int = 0, width: int = 2):
    x = x0
    while x < x1:
        draw.line([(x, y), (min(x + dash, x1), y)], fill=fill, width=width)
        x += dash + gap


# TODO: warning logs
class LabelImage:
    data: npt.NDArray
    image: Image.Image

    def __init__(self) -> Self:
        pass

    @staticmethod
    def from_path(path: Path) -> Self:
        if not path.exists() or not path.is_file():
            return

        img = LabelImage()
        img.image = Image.open(path)

        return img

    @classmethod
    def from_text_lines(
        cls,
        lines: list[str],
        width: int,
        font_path: Path,
        header: str | None = None,
        font_size: int = 34,
        header_size: int = 40,
        margin: int = 16,
        line_gap: int = 10,
    ) -> Self:
        font = ImageFont.truetype(str(font_path), font_size)
        header_font = ImageFont.truetype(str(font_path), header_size)

        line_h = font_size + line_gap
        header_h = (header_size + line_gap) if header else 0
        sep_h = margin  # space reserved for the separator rule + padding
        total_h = margin + header_h + sep_h + len(lines) * line_h + margin

        image = Image.new("L", (width, total_h), color=255)  # white background
        draw = ImageDraw.Draw(image)

        y = margin
        if header:
            draw.text((margin, y), header, fill=0, font=header_font)
            y += header_h
            _draw_dashed_line(draw, y + line_gap // 2, margin, width - margin)  # separator
            y += sep_h
        for name in lines:
            draw.text((margin, y), name, fill=0, font=font)
            y += line_h

        img = cls()
        img.image = image

        return img

    @classmethod
    def from_receipt(
        cls,
        items: list[tuple[str, str]],  # (label, amount) pairs, e.g. ("Markus (happiness)", "5,49 €")
        width: int,
        font_path: Path,
        total: str | None = None,
        total_label: str = "Summe:",
        header: str | None = None,
        font_size: int = 34,
        header_size: int = 40,
        margin: int = 16,
        line_gap: int = 10,
    ) -> Self:
        font = ImageFont.truetype(str(font_path), font_size)
        header_font = ImageFont.truetype(str(font_path), header_size)

        line_h = font_size + line_gap
        header_h = (header_size + line_gap) if header else 0
        sep_h = margin  # space reserved for a separator rule + padding
        total_block = (sep_h + line_h) if total is not None else 0
        total_h = margin + header_h + sep_h + len(items) * line_h + total_block + margin

        image = Image.new("L", (width, total_h), color=255)  # white background
        draw = ImageDraw.Draw(image)

        def _row(y: int, left: str, right: str):
            draw.text((margin, y), left, fill=0, font=font)
            right_w = draw.textlength(right, font=font)
            draw.text((width - margin - right_w, y), right, fill=0, font=font)  # right-aligned amount

        y = margin
        if header:
            draw.text((margin, y), header, fill=0, font=header_font)
            y += header_h
            _draw_dashed_line(draw, y + line_gap // 2, margin, width - margin)
            y += sep_h
        for left, right in items:
            _row(y, left, right)
            y += line_h
        if total is not None:
            _draw_dashed_line(draw, y + line_gap // 2, margin, width - margin)
            y += sep_h
            _row(y, total_label, total)

        img = cls()
        img.image = image

        return img

    def _scale(self, target_width: int):
        if self.image is None:
            return

        current_width, current_height = self.image.size
        ratio = current_width / current_height
        target_height = int(np.floor((1 / ratio) * target_width))

        self.image = self.image.resize((target_width, target_height))

        return target_height

    def _convert_grayscale(self):
        if self.image is None:
            return

        self.image = self.image.convert("L").convert("1", dither=Image.Dither.FLOYDSTEINBERG)

    def get_binary_data(self):
        if self.image is None:
            return

        image_bytes = np.packbits(np.invert(self.image)).tobytes()
        return image_bytes
