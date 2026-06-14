from pathlib import Path
from typing import Self

import numpy as np
from numpy import typing as npt
from PIL import Image


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
