import logging
from fractions import Fraction
from pathlib import Path

import av
from PIL import Image

logger = logging.getLogger(__name__)


PYAV_FORMAT_OPTIONS = {
    ".gif": {},
    ".mp4": {},
}

PIL_FORMAT_OPTIONS = {
    ".jpg": {"quality": 90, "optimize": True},
    ".webp": {"quality": 90, "method": 0, "lossless": False},
    ".avif": {"quality": 90, "speed": 10, "lossless": False},
}


def __pil_img_save(images: list[Image.Image], file_out: Path, durations: int | list[int] | tuple[int, ...] | None = None):
    try:
        format_params = PIL_FORMAT_OPTIONS[file_out.suffix.lower()]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported format: {file_out.suffix}") from exc

    sequence_params = {}
    if len(images) > 1:
        assert durations is not None, "when saving multiple images for an animation, duration per frame needs to be given!"

        # webp, gif and avif have the save_all option for animations, jpeg not.
        sequence_params = {
            "save_all": True,
            "append_images": images[1:] if len(images) > 1 else [],
            "duration": durations,  # config.duration,  # duration per frame in milliseconds. integer=all frames same, list/tuple individual.
            "loop": 0,  # loop forever
        }

    images[0].save(file_out, format=None, **format_params, **sequence_params)


def __pyav_mp4_save(images: list[Image.Image], file_out: Path, durations: int | list[int] | tuple[int, ...]):
    # ref https://github.com/PyAV-Org/PyAV/blob/main/examples/numpy/generate_video_with_pts.py
    if isinstance(durations, (list, tuple)):
        assert len(durations) == len(images)

    fps = 25
    in_img_w = images[0].width  # it is safe to assume all images have same dimensions
    in_img_h = images[0].height
    even_w = in_img_w if in_img_w % 2 == 0 else in_img_w - 1
    even_h = in_img_h if in_img_h % 2 == 0 else in_img_h - 1

    # set flag to crop. crop using PIL is more efficient than using reformatter to rescale by 1px.
    need_crop = (even_w, even_h) != (in_img_w, in_img_h)
    if need_crop:
        for i, image in enumerate(images):
            images[i] = image.crop(box=(0, 0, even_w, even_h))

    with av.open(file_out, mode="w") as container:
        stream = container.add_stream("h264", rate=fps, options={"crf": "20", "preset": "veryfast"})  # crf lower is better quality
        stream.time_base = Fraction(1, 1000)  # time base is now in milliseconds so we can directly assign the pts from duration
        stream.codec_context.time_base = Fraction(1, 1000)
        stream.width = even_w
        stream.height = even_h
        # high compat. # TODO: does this automatically reformat if the input is different or just states it should be yuv420?
        stream.pix_fmt = "yuv420p"

        my_pts = 0  # [milliseconds]
        for idx, image in enumerate(images):
            frame = av.VideoFrame.from_image(image)
            frame = frame.reformat(format="yuv420p")
            frame.pts = my_pts
            my_pts += durations[idx] if isinstance(durations, (list, tuple)) else durations

            for packet in stream.encode(frame):
                container.mux(packet)

        # duplicate last frame
        frame = av.VideoFrame.from_image(images[-1])
        frame.pts = my_pts
        for packet in stream.encode(frame):
            container.mux(packet)

        # Flush stream
        for packet in stream.encode():
            container.mux(packet)


def __pyav_gif_save(images: list[Image.Image], file_out: Path, durations: int | list[int] | tuple[int, ...]):
    if isinstance(durations, (list, tuple)):
        assert len(durations) == len(images)

    fps = 25

    with av.open(file_out, mode="w") as container:
        stream = container.add_stream("gif", rate=fps)
        stream.time_base = Fraction(1, 1000)  # time base is now in milliseconds so we can directly assign the pts from duration
        stream.codec_context.time_base = Fraction(1, 1000)
        stream.width = images[0].width
        stream.height = images[0].height
        stream.pix_fmt = "rgb8"

        my_pts = 0  # [milliseconds]
        for idx, image in enumerate(images):
            frame = av.VideoFrame.from_image(image)
            frame = frame.reformat(format="rgb8")
            frame.pts = my_pts

            my_pts += durations[idx] if isinstance(durations, (list, tuple)) else durations

            for packet in stream.encode(frame):
                container.mux(packet)

        # duplicate last frame
        frame = av.VideoFrame.from_image(images[-1])
        frame.pts = my_pts
        for packet in stream.encode(frame):
            container.mux(packet)

        # Flush stream
        for packet in stream.encode():
            container.mux(packet)


def encode(images: list[Image.Image], file_out: Path, durations: int | list[int] | tuple[int, ...] | None = None):
    save_to_format = file_out.suffix.lower()

    if save_to_format in PIL_FORMAT_OPTIONS.keys():
        __pil_img_save(images, file_out, durations)
    elif save_to_format == ".mp4":
        assert durations is not None
        __pyav_mp4_save(images, file_out, durations)
    elif save_to_format == ".gif":
        assert durations is not None
        __pyav_gif_save(images, file_out, durations)
    else:
        raise RuntimeError(f"format {save_to_format} is not supported!")
