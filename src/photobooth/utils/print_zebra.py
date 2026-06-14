import subprocess
import sys
from functools import reduce
from pathlib import Path

import numpy as np

from .image import LabelImage


def f(a, b):
    return (a << 1) | b


def bools_to_int(arr):
    return reduce(f, arr)


ESC_HEX = 0x1B
RS_HEX = 0x1E
S_LOWER_HEX = 0x73
P_LOWER_HEX = 0x70
AND_HEX = 0x26
DPI = 203
TO_INCH = 1 / 25.4
# mm
LABEL_WIDTH = 80


def write_data():
    print([ESC_HEX, S_LOWER_HEX, 2, 255, 255])
    data = bytearray(
        [
            ESC_HEX,
            S_LOWER_HEX,
            10,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            ESC_HEX,
            S_LOWER_HEX,
            10,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            ESC_HEX,
            S_LOWER_HEX,
            10,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
            255,
        ]
    )
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def cut():
    data = bytearray([RS_HEX, 50])
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def print_test_page():
    data = bytearray([ESC_HEX, 0x50, 0x05])
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def set_print_speed(speed: int):
    data = bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 8, speed])
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def set_compensation_mode(thermal=True, speed=True, secondary=True):
    value = bools_to_int([thermal, speed, secondary])
    data = bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 80, value])
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def set_secondary_burn_time(burn_time: int = 120):
    data = bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 6, *(burn_time.to_bytes(2))])
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def set_burn_time(burn_time: int = 546):
    data = bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 7, *(burn_time.to_bytes(2))])
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=data)


def main():
    path = Path(sys.argv[1])
    label: LabelImage = LabelImage.from_path(path)

    target_width = int(np.floor(LABEL_WIDTH * TO_INCH * DPI))
    target_width -= target_width % 8

    target_height = label._scale(target_width=target_width)
    label._convert_grayscale()
    data = label.get_binary_data()

    print_data = bytearray()
    row_size = int(target_width / 8)
    for i in range(target_height):
        print_data += bytearray([ESC_HEX, S_LOWER_HEX, row_size])
        print_data += data[i * row_size : i * row_size + row_size]

    set_compensation_mode(True, False, True)
    set_print_speed(80)
    set_burn_time(570)
    set_secondary_burn_time(120)
    subprocess.run(["lp", "-d", "zr", "-o", "raw"], input=print_data)
    cut()


if __name__ == "__main__":
    main()
