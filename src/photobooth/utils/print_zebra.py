import sys
from pathlib import Path

import numpy as np

from .image import LabelImage
from .zebra_printer import ZebraPrinter

DPI = 203
TO_INCH = 1 / 25.4
LABEL_WIDTH = 80  # mm
FONT_PATH = Path(__file__).parent.parent.parent.parent / "userdata" / "nerdfontmono-reg.ttf"
NAMES_HEADER = "Rechnung:"  # editable; matches the German template wording
TOTAL_LABEL = "Summe:"

# Fantasy pricing: a confidently happy face earns a discount, an angry/disgusted one a surcharge.
# The emotion score (0..1) scales how far the emotion moves the price from BASE_PRICE. Edit freely.
BASE_PRICE = 9.99
PRICE_FLOOR = 0.50
EMOTION_WEIGHTS = {
    "happiness": -0.5,
    "surprise": 0.25,
    "neutral": 0.0,
    "sadness": 0.4,
    "fear": 0.5,
    "contempt": 0.6,
    "disgust": 0.7,
    "anger": 1.0,
}


def fantasy_price(emotion: str, score: float) -> float:
    weight = EMOTION_WEIGHTS.get(emotion, 0.0)
    return max(BASE_PRICE * (1 + weight * score), PRICE_FLOOR)


def format_price(amount: float) -> str:
    return f"{amount:.2f} €".replace(".", ",")  # german decimal comma, e.g. "5,49 €"


def _split_arg(index: int) -> list[str]:
    return [v.strip() for v in sys.argv[index].split(",")] if len(sys.argv) > index else []


def main():
    path = Path(sys.argv[1])
    # argv[2..4] are comma-separated, index-aligned {face_names}/{face_emotions}/{face_emotion_scores}
    names = _split_arg(2)
    emotions = _split_arg(3)
    scores = _split_arg(4)
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

    items: list[tuple[str, str]] = []
    total = 0.0
    for i, name in enumerate(names):
        if not name:
            continue
        emotion = emotions[i] if i < len(emotions) else ""
        try:
            score = float(scores[i]) if i < len(scores) and scores[i] else 0.0
        except ValueError:
            score = 0.0
        price = fantasy_price(emotion, score)
        total += price
        left = f"{name} ({emotion})" if emotion else name
        items.append((left, format_price(price)))

    if items:
        receipt = LabelImage.from_receipt(
            items,
            width=target_width,
            font_path=FONT_PATH,
            total=format_price(total),
            total_label=TOTAL_LABEL,
            header=NAMES_HEADER,
        )
        receipt._convert_grayscale()
        receipt_data = receipt.get_binary_data()
        assert receipt_data is not None
        receipt_height = receipt.image.size[1]
        printer.write_image_rows(receipt_data, row_size=int(target_width / 8), height=receipt_height)

    printer.cut()
    printer.print()


if __name__ == "__main__":
    main()
