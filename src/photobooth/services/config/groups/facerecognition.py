"""AppConfig class providing central config for face recognition."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GroupFaceRecognition(BaseModel):
    """Configure face recognition service."""

    model_config = ConfigDict(title="Face Recognition Config")

    enabled: bool = Field(
        default=False,
        description="Enable face recognition. Requires insightface and onnxruntime. When disabled, {face_names} resolves to empty string.",
    )

    model_pack: Literal["buffalo_s", "buffalo_m", "buffalo_l"] = Field(
        default="buffalo_m",
        description="insightface model pack for detection + recognition. buffalo_s=fastest (SCRFD-500MF + MobileFace), "
        "buffalo_m=balanced (default), buffalo_l=most accurate (SCRFD-10GF + ArcFace-R50, ~326MB). Larger packs "
        "detect small/profile/low-light faces better but are slower on CPU and download more on first use.",
    )

    data_folder: Path = Field(
        default=Path("./userdata/facerecognition"),
        description="Folder containing known face images. Structure: <data_folder>/<person_name>/*.jpg",
    )

    cosine_threshold: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Cosine similarity threshold for ArcFace embeddings. Higher = stricter (fewer false positives).",
    )

    predict_emotions: bool = Field(
        default=False,
        description="Additionally predict each recognized person's emotion, exposed as {face_emotions} and "
        "{face_emotion_scores}. Loads an extra ONNX model (HSEmotion). When disabled, both resolve to empty string.",
    )
