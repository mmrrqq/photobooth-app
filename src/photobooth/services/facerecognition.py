"""Face recognition service using insightface (buffalo_s: SCRFD + ArcFace)."""

import logging
from pathlib import Path

import cv2
import numpy as np

from ..appconfig import appconfig
from .base import BaseService

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


class FaceRecognitionService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._app = None
        self._known_faces: list[tuple[str, np.ndarray]] = []

    def start(self) -> None:
        super().start()

        if not appconfig.facerecognition.enabled:
            logger.info("FaceRecognitionService disabled via config.")
            super().disabled()
            return

        try:
            from insightface.app import FaceAnalysis

            self._app = FaceAnalysis(
                name="buffalo_s",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))
        except Exception as exc:
            logger.error(f"Failed to initialize insightface, disabling service: {exc}")
            super().disabled()
            return

        data_folder = Path(appconfig.facerecognition.data_folder)
        if data_folder.exists():
            self._load_known_faces(data_folder)
        else:
            logger.warning(f"Face recognition data folder not found: {data_folder}")

        logger.info(f"FaceRecognitionService started. Known persons: {self._known_person_names()}")
        super().started()

    def stop(self) -> None:
        super().stop()
        self._app = None
        self._known_faces.clear()
        super().stopped()

    def identify_faces(self, image_path: Path) -> list[str]:
        """Detect and identify faces in an image. Returns [] on any error or when disabled."""
        if not self.is_running() or self._app is None or not self._known_faces:
            return []

        try:
            img = cv2.imread(str(image_path))
            if img is None:
                logger.warning(f"Could not read image: {image_path}")
                return []

            faces = self._app.get(img)
            threshold = appconfig.facerecognition.cosine_threshold
            identified: list[str] = []

            for face in faces:
                query_emb = face.normed_embedding
                best_name: str | None = None
                best_score: float = -1.0

                for name, known_emb in self._known_faces:
                    score = float(np.dot(query_emb, known_emb))
                    if score > best_score:
                        best_score = score
                        best_name = name

                if best_name is not None and best_score >= threshold and best_name not in identified:
                    identified.append(best_name)

            return identified

        except Exception:
            logger.exception("Error during face identification")
            return []

    def _load_known_faces(self, data_folder: Path) -> None:
        assert self._app is not None

        for person_dir in sorted(data_folder.iterdir()):
            if not person_dir.is_dir():
                continue

            person_name = person_dir.name
            person_embeddings: list[np.ndarray] = []

            image_files = [f for f in sorted(person_dir.iterdir()) if f.suffix.lower() in _IMAGE_EXTENSIONS]
            if not image_files:
                logger.warning(f"No images found for '{person_name}' in {person_dir}")
                continue

            for img_path in image_files:
                img = cv2.imread(str(img_path))
                if img is None:
                    logger.warning(f"Could not read {img_path}, skipping")
                    continue

                faces = self._app.get(img)
                if not faces:
                    logger.warning(f"No face detected in {img_path}, skipping")
                    continue

                if len(faces) > 1:
                    logger.warning(f"Multiple faces in {img_path}, using highest-confidence face")

                person_embeddings.append(faces[0].normed_embedding)

            if not person_embeddings:
                logger.warning(f"No usable embeddings for '{person_name}', skipping")
                continue

            mean_emb = np.mean(np.stack(person_embeddings), axis=0)
            norm = np.linalg.norm(mean_emb)
            if norm > 0:
                mean_emb = mean_emb / norm

            self._known_faces.append((person_name, mean_emb))
            logger.info(f"Loaded {len(person_embeddings)} reference image(s) for '{person_name}'")

    def _known_person_names(self) -> list[str]:
        return [name for name, _ in self._known_faces]
