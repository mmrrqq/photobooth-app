from pathlib import Path
from typing import Literal

from sqlalchemy import String, TypeDecorator

MediaitemTypes = Literal["image", "collage", "animation", "video", "multicamera"]
# SQLalchemy persists the name, fastapi validates against the value.
# Ref: https://github.com/fastapi/fastapi/discussions/11098
# was strEnum before but using literal type is 1:1 transparent in db use and simplifies usage in the config/jsonforms renderer
# image:        captured single image that is NOT part of a collage (normal process)
# collage:      canvas image that was made out of several collage_image
# animation:    canvas image that was made out of several animation_image
# video:        captured video - h264, mp4 is currently well supported in browsers it seems
# multicamera:  video - h264, mp4, result of multicamera image, example the wigglegram

DimensionTypes = Literal["full", "preview", "thumbnail"]


class PathType(TypeDecorator):
    impl = String

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        else:
            return str(value)

    def process_result_value(self, value, dialect):
        # assert value is not None
        if value is None:
            return None
        else:
            return Path(value)
