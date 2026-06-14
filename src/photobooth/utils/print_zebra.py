import sys
from pathlib import Path

import numpy as np

from .image import LabelImage
from .zebra_printer import ZebraPrinter

DPI = 203
TO_INCH = 1 / 25.4
LABEL_WIDTH = 80  # mm


def main():
    path = Path(sys.argv[1])
    label: LabelImage = LabelImage.from_path(path)
    pre_label: LabelImage = LabelImage.from_path(Path(__file__).parent / "receipt_template.png")

    target_width = int(np.floor(LABEL_WIDTH * TO_INCH * DPI))
    target_width -= target_width % 8

    pre_label_height = pre_label._scale(target_width=target_width)
    assert pre_label_height is not None
    pre_label._convert_grayscale()
    pre_label_data = pre_label.get_binary_data()
    assert pre_label_data is not None

    target_height = label._scale(target_width=target_width)
    assert target_height is not None
    label._convert_grayscale()
    data = label.get_binary_data()
    assert data is not None

    printer = ZebraPrinter()
    printer.set_compensation_mode(True, False, True)
    printer.set_print_speed(90)
    printer.set_burn_time(570)
    printer.set_secondary_burn_time(120)
    printer.write_image_rows(pre_label_data, row_size=int(target_width / 8), height=pre_label_height)
    printer.write_image_rows(data, row_size=int(target_width / 8), height=target_height)
    printer.cut()
    printer.print()


if __name__ == "__main__":
    main()
