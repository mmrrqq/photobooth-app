import logging
from pathlib import Path
from subprocess import PIPE, Popen

import av
import pytest
from PIL import Image, ImageSequence
from turbojpeg import TurboJPEG

from ..tests.util import dummy_animation

turbojpeg = TurboJPEG()
logger = logging.getLogger(name=None)


def ffmpeg_hq_optimizedquality_scale(gif_filepath: Path, tmp_path):
    # https://engineering.giphy.com/how-to-make-gifs-with-ffmpeg/
    ffmpeg_subprocess = Popen(
        [
            "ffmpeg",
            "-y",  # overwrite with no questions
            "-i",
            str(gif_filepath),
            "-vf",
            "scale=1000:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            str(tmp_path / "ffmpeg_hq_optimizedquality_scale.gif"),  # https://docs.python.org/3/library/pathlib.html#operators
        ]
    )
    code = ffmpeg_subprocess.wait()
    if code != 0:
        raise AssertionError("process fail")


def ffmpeg_hq_optimizedspeed_scale(gif_filepath: Path, tmp_path):
    # https://engineering.giphy.com/how-to-make-gifs-with-ffmpeg/
    ffmpeg_subprocess = Popen(
        [
            "ffmpeg",
            "-y",  # overwrite with no questions
            "-i",
            str(gif_filepath),
            "-vf",
            "scale=1000:-1:flags=bicubic,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            str(tmp_path / "ffmpeg_hq_optimizedspeed_scale.gif"),  # https://docs.python.org/3/library/pathlib.html#operators
        ]
    )
    code = ffmpeg_subprocess.wait()
    if code != 0:
        raise AssertionError("process fail")


def ffmpeg_stdin_scale(gif_filepath: Path, tmp_path):
    ffmpeg_subprocess = Popen(
        [
            "ffmpeg",
            "-y",  # overwrite with no questions
            "-f",  # force input or output format
            "image2pipe",
            "-i",
            "-",
            "-vf",
            "scale=1000:-1:flags=bicubic,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
            str(tmp_path / "ffmpeg_stdin_scale.gif"),  # https://docs.python.org/3/library/pathlib.html#operators
        ],
        stdin=PIPE,
    )
    assert ffmpeg_subprocess.stdin
    ffmpeg_subprocess.stdin.write(gif_filepath.read_bytes())
    ffmpeg_subprocess.stdin.close()
    code = ffmpeg_subprocess.wait()
    if code != 0:
        raise AssertionError("process fail")


def pil_scale(gif_filepath: Path, tmp_path):
    gif_image = Image.open(gif_filepath, formats=["gif"])

    # Wrap on-the-fly thumbnail generator
    def thumbnails(frames: ImageSequence.Iterator):
        for frame in frames:
            thumbnail = frame.copy()
            thumbnail.thumbnail(size=target_size, resample=Image.Resampling.BICUBIC)
            yield thumbnail

    # to recover the original durations in scaled versions
    durations = []
    for frame in ImageSequence.Iterator(gif_image):
        frame.load()
        duration = frame.info.get("duration", 1000)  # fallback 1sec if info not avail.
        durations.append(duration)

    # determine target size
    target_size = (1000, 800)

    # Get sequence iterator
    frames = ImageSequence.Iterator(gif_image)
    resized_frames = thumbnails(frames)

    # Save output
    om = next(resized_frames)  # Handle first frame separately
    om.info = gif_image.info  # Copy original information (duration is only for first frame so on save handled separately)
    om.save(
        str(tmp_path / "out_animation.gif"),
        format="gif",
        save_all=True,
        append_images=list(resized_frames),
        duration=durations,
        optimize=True,
        loop=0,  # loop forever
    )


def pyav_rescale_gif(gif_filepath: Path, tmp_path: Path, target_max_size=1000):
    # --- INPUT ---
    container_in = av.open(gif_filepath)
    stream_in = container_in.streams.video[0]
    tb_in = stream_in.time_base  # GIF timebase (usually 1/100)
    assert tb_in

    # --- Determine output size from first frame only ---
    first_frame = next(container_in.decode(stream_in))
    w, h = first_frame.width, first_frame.height

    scale = target_max_size / max(w, h)
    if scale < 1.0:
        new_w = int(w * scale)
        new_h = int(h * scale)
    else:
        new_w, new_h = w, h

    # Rewind
    container_in.seek(0)

    # --- OUTPUT ---
    out_path = tmp_path / "out_animation.gif"
    container_out = av.open(out_path, mode="w")

    stream_out = container_out.add_stream("gif", rate=25)
    stream_out.time_base = tb_in
    stream_out.codec_context.time_base = tb_in
    stream_out.width = new_w
    stream_out.height = new_h
    stream_out.pix_fmt = "rgb8"

    last_pts = 0
    last_rescaled = None

    # --- STREAMING DECODE → RESCALE → ENCODE ---
    for frame in container_in.decode(stream_in):
        # Extract duration from GIF frame
        dur = frame.duration
        frame.pts = last_pts
        last_pts += dur

        # Rescale + convert to rgb8 using libswscale
        rescaled = frame.reformat(width=new_w, height=new_h, format="rgb8", interpolation="BICUBIC")
        last_rescaled = rescaled

        for packet in stream_out.encode(rescaled):
            container_out.mux(packet)

    # --- Duplicate last frame ---
    if last_rescaled is not None:
        dup = last_rescaled
        dup.pts = last_pts
        for packet in stream_out.encode(dup):
            container_out.mux(packet)

    # --- Flush ---
    for packet in stream_out.encode():
        container_out.mux(packet)

    container_out.close()
    container_in.close()


@pytest.fixture(
    params=[
        "pil_scale",
        "ffmpeg_stdin_scale",
        "ffmpeg_hq_optimizedquality_scale",
        "ffmpeg_hq_optimizedspeed_scale",
        "pyav_rescale_gif",
    ]
)
def library(request):
    # yield fixture instead return to allow for cleanup:
    yield request.param


def image(file) -> bytes:
    with open(file, "rb") as file:
        in_file_read = file.read()

    return in_file_read


@pytest.mark.benchmark(group="scalegif")
def test_libraries_scalegif(library, benchmark, tmp_path):
    dummy_animation_file = tmp_path / "in_animation.gif"
    dummy_animation(dummy_animation_file, (1920, 1080))
    benchmark(eval(library), gif_filepath=dummy_animation_file, tmp_path=tmp_path)
    assert True
