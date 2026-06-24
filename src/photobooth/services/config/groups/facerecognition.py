"""AppConfig class providing central config for face recognition."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class GroupFaceRecognition(BaseModel):
    """Configure face recognition service."""

    model_config = ConfigDict(title="Face Recognition Config")

    enabled: bool = Field(
        default=False,
        description="Enable face recognition. Requires insightface and onnxruntime-gpu. When disabled, {face_names} resolves to empty string.",
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
