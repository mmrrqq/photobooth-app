import subprocess
from functools import reduce

ESC_HEX = 0x1B
RS_HEX = 0x1E
S_LOWER_HEX = 0x73
P_LOWER_HEX = 0x70
AND_HEX = 0x26


def _bools_to_int(arr) -> int:
    return reduce(lambda a, b: (a << 1) | b, arr)


class ZebraPrinter:
    def __init__(self, printer_name: str = "zr"):
        self._printer_name = printer_name
        self._buffer = bytearray()

    def write_data(self):
        row = bytearray([ESC_HEX, S_LOWER_HEX, 10] + [0xFF] * 10)
        self._buffer += row * 3

    def cut(self):
        self._buffer += bytearray([RS_HEX, 50])

    def print_test_page(self):
        self._buffer += bytearray([ESC_HEX, 0x50, 0x05])

    def set_print_speed(self, speed: int):
        self._buffer += bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 8, speed])

    def set_compensation_mode(self, thermal: bool = True, speed: bool = True, secondary: bool = True):
        value = _bools_to_int([thermal, speed, secondary])
        self._buffer += bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 80, value])

    def set_secondary_burn_time(self, burn_time: int = 120):
        self._buffer += bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 6, *(burn_time.to_bytes(2))])

    def set_burn_time(self, burn_time: int = 546):
        self._buffer += bytearray([ESC_HEX, AND_HEX, P_LOWER_HEX, 7, *(burn_time.to_bytes(2))])

    def write_image_rows(self, data: bytes, row_size: int, height: int):
        for i in range(height):
            self._buffer += bytearray([ESC_HEX, S_LOWER_HEX, row_size])
            self._buffer += data[i * row_size : i * row_size + row_size]

    def print(self):
        subprocess.run(["lp", "-d", self._printer_name, "-o", "raw"], input=self._buffer)
        self._buffer = bytearray()
