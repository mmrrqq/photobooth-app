import io
import logging
import tempfile
from collections.abc import Generator
from fractions import Fraction
from typing import Any

import av
import pytest
from PIL import Image

logger = logging.getLogger(name=None)


@pytest.fixture
def dummy_images() -> Generator[list[Image.Image], Any, None]:
    yield [
        Image.open("src/tests/assets/input_lores.jpg"),
        Image.open("src/tests/assets/input_lores.jpg").rotate(180),
        Image.open("src/tests/assets/input_lores.jpg"),
        Image.open("src/tests/assets/input_lores.jpg").rotate(180),
        Image.open("src/tests/assets/input_lores.jpg"),
        Image.open("src/tests/assets/input_lores.jpg").rotate(180),
    ]


def pillow_encode_gif(images: list[Image.Image]):
    byte_io = io.BytesIO()
    ## create mediaitem
    images[0].save(
        byte_io,
        format="gif",
        save_all=True,
        append_images=images[1:] if len(images) > 1 else [],
        optimize=True,
        # duration per frame in milliseconds. integer=all frames same, list/tuple individual.
        duration=125,
        loop=0,  # loop forever
    )

    bytes_full = byte_io.getbuffer()
    # Path("file.gif").write_bytes(bytes_full)
    return bytes_full


def pillow_encode_webp(images: list[Image.Image]):
    byte_io = io.BytesIO()
    ## create mediaitem
    images[0].save(
        byte_io,
        format="WebP",
        save_all=True,
        append_images=images[1:] if len(images) > 1 else [],
        quality=85,
        method=0,
        lossless=False,
        duration=125,
        loop=0,  # loop forever
    )

    bytes_full = byte_io.getbuffer()
    # Path("file.webp").write_bytes(bytes_full)
    return bytes_full


def pillow_encode_avif(images: list[Image.Image]):
    byte_io = io.BytesIO()
    ## create mediaitem
    images[0].save(
        byte_io,
        format="AVIF",
        save_all=True,
        append_images=images[1:] if len(images) > 1 else [],
        quality=85,
        speed=10,
        lossless=False,
        duration=125,
        loop=0,  # loop forever
    )

    bytes_full = byte_io.getbuffer()
    # Path("file.avif").write_bytes(bytes_full)
    return bytes_full


def pyav_encode_mp4(images: list[Image.Image], frame_duration: int = 125):
    # ref https://github.com/PyAV-Org/PyAV/blob/main/examples/numpy/generate_video_with_pts.py
    fps = round(1.0 / (frame_duration / 1000.0))  # frame_duration is in [ms], normize to [s] for pyav

    n = len(images)
    cycle = [*range(n), *range(n - 2, 0, -1)]
    repeat = 1
    sequence = cycle * repeat

    in_img_w = images[0].width  # it is safe to assume all images have same dimensions
    in_img_h = images[0].height

    even_w = in_img_w if in_img_w % 2 == 0 else in_img_w - 1
    even_h = in_img_h if in_img_h % 2 == 0 else in_img_h - 1
    # set flag to crop. crop using PIL is more efficient than using reformatter to rescale by 1px.
    need_crop = (even_w, even_h) != (in_img_w, in_img_h)

    if need_crop:
        for i, image in enumerate(images):
            images[i] = image.crop(box=(0, 0, even_w, even_h))

    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        container = av.open(tmp.name, mode="w")
        stream = container.add_stream("h264", rate=fps, options={"crf": "28", "preset": "veryfast"})  # crf lower is better quality
        stream.codec_context.time_base = Fraction(1, fps)
        stream.width = even_w
        stream.height = even_h
        # high compat. # TODO: does this automatically reformat if the input is different or just states it should be yuv420?
        stream.pix_fmt = "yuv420p"

        my_pts = 0  # [seconds]
        for idx in sequence:
            frame = av.VideoFrame.from_image(images[idx])
            # frame = frame.reformat(format="yuv420p")# TODO: needed?
            frame.pts = my_pts
            my_pts += 1.0

            for packet in stream.encode(frame):
                container.mux(packet)

        # last frame duplication seems not needed here, it plays correctly without

        # Flush stream
        for packet in stream.encode():
            container.mux(packet)

        # Close the file
        container.close()

        return tmp.read()  # bytes of the encoded file


def pyav_encode_gif(images: list[Image.Image], frame_duration: int = 125):
    # ref https://github.com/PyAV-Org/PyAV/blob/main/examples/numpy/generate_video_with_pts.py
    fps = round(1.0 / (frame_duration / 1000.0))  # frame_duration is in [ms], normize to [s] for pyav

    n = len(images)
    cycle = [*range(n), *range(n - 2, 0, -1)]
    repeat = 1
    sequence = cycle * repeat

    with tempfile.NamedTemporaryFile(suffix=".gif", delete=False) as tmp:
        container = av.open(tmp.name, mode="w")
        stream = container.add_stream("gif", rate=fps)
        # stream.codec_context.time_base = Fraction(1, fps)
        stream.width = images[0].width
        stream.height = images[0].height
        stream.pix_fmt = "rgb8"

        my_pts = 0  # [seconds]
        for idx in sequence:
            frame = av.VideoFrame.from_image(images[idx])

            frame = frame.reformat(format="rgb8")
            frame.pts = my_pts
            my_pts += 1.0

            for packet in stream.encode(frame):
                container.mux(packet)

        # last frame duplication seems not needed here, it plays correctly without

        # Flush stream
        for packet in stream.encode():
            container.mux(packet)

        # Close the file
        container.close()
        # shutil.copy(tmp.name, "test.gif")
        return tmp.read()  # bytes of the encoded file


def pyav_encode_avif(images: list[Image.Image], frame_duration: int = 125):
    # ref https://github.com/PyAV-Org/PyAV/blob/main/examples/numpy/generate_video_with_pts.py
    fps = round(1.0 / (frame_duration / 1000.0))  # frame_duration is in [ms], normize to [s] for pyav
    print(av.codecs_available)
    n = len(images)
    cycle = [*range(n), *range(n - 2, 0, -1)]
    repeat = 1
    sequence = cycle * repeat

    with tempfile.NamedTemporaryFile(suffix=".avif", delete=False) as tmp:
        container = av.open(tmp.name, mode="w")
        stream = container.add_stream("libsvtav1", rate=fps)
        assert isinstance(stream, av.VideoStream)
        # stream.codec_context.time_base = Fraction(1, fps)
        stream.width = images[0].width
        stream.height = images[0].height
        stream.pix_fmt = "yuv420p10le"
        # 3. SVT-AV1 spezifische Parameter setzen
        stream.options = {
            "crf": "26",  # Qualität (0-63, niedriger = besser)
            "preset": "10",  # größer= höhere Geschwindigkeit (0-13, 6-8 ist optimal für Alltag)
            "svtav1-params": "tune=0",  # 0 = Visuelle Qualität (VQ), 1 = PSNR
        }

        my_pts = 0  # [seconds]
        for idx in sequence:
            frame = av.VideoFrame.from_image(images[idx])

            frame = frame.reformat(format="yuv420p10le")
            frame.pts = my_pts
            my_pts += 1.0

            for packet in stream.encode(frame):
                container.mux(packet)

        # last frame duplication seems not needed here, it plays correctly without

        # Flush stream
        for packet in stream.encode():
            container.mux(packet)

        # Close the file
        container.close()
        # shutil.copy(tmp.name, "test.avif")
        return tmp.read()  # bytes of the encoded file


def pyav_encode_webp(images: list[Image.Image], frame_duration: int = 125):
    # ref https://github.com/PyAV-Org/PyAV/blob/main/examples/numpy/generate_video_with_pts.py
    fps = round(1.0 / (frame_duration / 1000.0))  # frame_duration is in [ms], normize to [s] for pyav
    print(av.codecs_available)
    n = len(images)
    cycle = [*range(n), *range(n - 2, 0, -1)]
    repeat = 1
    sequence = cycle * repeat

    with tempfile.NamedTemporaryFile(suffix=".webp", delete=False) as tmp:
        container = av.open(tmp.name, mode="w")
        stream = container.add_stream("libwebp", rate=fps)
        assert isinstance(stream, av.VideoStream)
        # stream.codec_context.time_base = Fraction(1, fps)
        stream.width = images[0].width
        stream.height = images[0].height
        stream.pix_fmt = "yuv420p"
        # 3. WebP-spezifische Optionen setzen
        stream.options = {
            "lossless": "0",  # 0 = Verlustbehaftet (kleine Datei), 1 = Verlustfrei (groß)
            "quality": "80",  # Qualität von 0-100 (nur aktiv bei lossless=0)
            "compression_level": "2",  # Encoding-Aufwand von 0-6 (höher = kleinere Datei, langsamer)
            "loop": "0",  # 0 bedeutet unendlicher Loop (Standard)
        }

        my_pts = 0  # [seconds]
        for idx in sequence:
            frame = av.VideoFrame.from_image(images[idx])

            frame = frame.reformat(format="yuv420p")
            frame.pts = my_pts
            my_pts += 1.0

            for packet in stream.encode(frame):
                container.mux(packet)

        # last frame duplication seems not needed here, it plays correctly without

        # Flush stream
        for packet in stream.encode():
            container.mux(packet)

        # Close the file
        container.close()
        # shutil.copy(tmp.name, "test.webp")
        return tmp.read()  # bytes of the encoded file


@pytest.fixture(
    params=[
        "pillow_encode_gif",
        "pillow_encode_webp",
        "pillow_encode_avif",
        "pyav_encode_mp4",
        "pyav_encode_gif",
        "pyav_encode_avif",
        "pyav_encode_webp",
    ]
)
def library(request):
    yield request.param


# needs pip install pytest-benchmark
@pytest.mark.benchmark(group="encode_animation")
def test_encode_animation(library, dummy_images, benchmark):
    benchmark(eval(library), images=dummy_images)
    assert True
