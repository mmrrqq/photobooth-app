import io
import logging
import shutil
import time
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

import av
import numpy as np
import piexif
from PIL import Image, ImageChops

from photobooth import PATH_CAMERA_ORIGINAL, PATH_PROCESSED
from photobooth.database.models import Mediaitem
from photobooth.services.backends.abstractbackend import AbstractBackend
from photobooth.utils.helper import filename_str_time

logger = logging.getLogger(name=None)


def block_until_device_is_running(backend: AbstractBackend):
    """Mostly used for testing to ensure the device is up."""

    counter = 0
    while not backend.is_running():
        logger.debug("wait for startup")
        time.sleep(0.5)
        counter += 1

        if counter == 20:  # max 10s
            raise RuntimeError("abort waiting for startup!")


def get_images(backend: AbstractBackend, multicam_is_error: bool = False):
    try:
        with Image.open(backend.wait_for_still_file()) as img:
            img.verify()
    except Exception as exc:
        raise AssertionError(f"backend did not return valid image bytes, {exc}") from exc

    try:
        with Image.open(io.BytesIO(backend.wait_for_lores_image())) as img:
            img.verify()
    except Exception as exc:
        raise AssertionError(f"backend did not return valid image bytes, {exc}") from exc
    try:
        for path in backend.wait_for_multicam_files():
            with Image.open(path) as img:
                img.verify()
    except Exception as exc:
        if multicam_is_error:
            raise AssertionError(f"backend did not return valid image bytes, {exc}") from exc


def is_same(img1: Image.Image, img2: Image.Image):
    # ensure rgb for both before compare, kind of ignore transparency.
    img1 = img1.convert("RGB")
    img2 = img2.convert("RGB")

    # img1.show()
    # img2.show()

    diff = ImageChops.difference(img2, img1)
    logger.info(diff.getbbox())

    # getbbox returns None if all same, otherwise anything that is evalued to false
    return not bool(diff.getbbox())


def video_duration(path: str | Path) -> float:
    with av.open(path) as container:
        dur = float(container.streams[0].duration or 0)
        tb = container.streams[0].time_base
        assert dur, "cannot determine duration (ticks)"
        assert tb, "cannot determine timebase (s/tick)"

        return float(dur * tb)


def get_exiforiented_jpeg(jpeg_bytes_io: io.BytesIO, orientation: int) -> io.BytesIO:
    exif_dict = {"0th": {piexif.ImageIFD.Orientation: orientation}}
    exif_bytes = piexif.dump(exif_dict)

    out_jpeg_bytes_io = io.BytesIO()
    piexif.insert(exif_bytes, jpeg_bytes_io.getvalue(), out_jpeg_bytes_io)

    return out_jpeg_bytes_io


def get_jpeg(dim: tuple[int, int]) -> io.BytesIO:
    im = Image.new("L", dim, "red")
    jpeg_bytes_io = io.BytesIO()
    im.save(jpeg_bytes_io, "jpeg")
    return jpeg_bytes_io


def dummy_mediaitem():
    img = Image.new("RGB", (600, 400), color="grey")
    img_path_original = Path(
        NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=PATH_CAMERA_ORIGINAL,
            prefix=f"{filename_str_time()}_pytest_dummy_",
            suffix=".jpg",
        ).name  # name from namedtemporaryfile is the whole path.
    )
    # absolute path's dont work for us, make it relative to home.
    img_path_original = img_path_original.relative_to(Path.cwd())

    img.save(img_path_original)
    shutil.copy(img_path_original, PATH_PROCESSED)

    new_item_instance = Mediaitem(
        job_identifier=uuid4(),
        media_type="image",
        captured_original=img_path_original,
        processed=Path(PATH_PROCESSED, img_path_original.name),
        pipeline_config={},
        show_in_gallery=True,
    )

    return new_item_instance


def dummy_animation(filepath: Path, size=(600, 400), num_frames: int = 6, noise_std=100):

    frames = []

    for _ in range(num_frames):
        arr = np.random.normal(127, noise_std, (size[1], size[0], 3)).clip(0, 255).astype(np.uint8)
        frames.append(Image.fromarray(arr, "RGB"))

    durations = [200 + i * 50 for i in range(len(frames))]

    frames[0].save(
        filepath,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )


def get_impl_func_for_plugin(plugin, hook):
    # FIXME: not sure yet, why patch.object(GpioLights,"sm_on_enter_state") does not assert_called() eval True but is still correctly called...
    # working around currently with this function:
    for hookimpl in hook.get_hookimpls():
        if hookimpl.plugin == plugin:  # Match specific plugin instance
            return hookimpl

    # if no plugin matched, we raise an error
    raise AssertionError("Plugin's hook implementation was not found!")
