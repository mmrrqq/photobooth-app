"""Face recognition service using insightface (configurable buffalo_* pack: SCRFD + ArcFace)."""

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..appconfig import appconfig
from ..utils.rembg.sessions.base import BaseSession
from .base import BaseService

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

# HSEmotion emotion classifier (EfficientNet-B0, AffectNet 8-class): input [batch,3,224,224] RGB float,
# ImageNet-normalized; output [batch,8] logits. Tensor names + input size are read dynamically.
# To use the more accurate (heavier) enet_b2_8 instead, swap the three constants below; preprocessing
# auto-adapts to its 260x260 input.
EMOTION_MODEL_FILENAME = "enet_b0_8_best_vgaf.onnx"
EMOTION_MODEL_URL = "https://github.com/av-savchenko/face-emotion-recognition/raw/main/models/affectnet_emotions/onnx/enet_b0_8_best_vgaf.onnx"
EMOTION_MODEL_MD5 = "d24f488784768353af699427678c8e8b"
# AffectNet 8-class order used by HSEmotion (idx_to_class), lowercased.
EMOTION_LABELS = ["anger", "contempt", "disgust", "fear", "happiness", "neutral", "sadness", "surprise"]
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


@dataclass
class RecognizedFace:
    name: str
    emotion: str  # "" when emotion prediction is disabled/unavailable
    emotion_score: float  # softmax confidence 0.0-1.0 of `emotion`; 0.0 when unavailable


class _EmotionClassifier:
    """Standalone FER+ ONNX classifier run on face crops produced by insightface."""

    def __init__(self, providers: list[str]) -> None:
        import onnxruntime as ort

        model_path = BaseSession.models_download_home() / EMOTION_MODEL_FILENAME
        BaseSession.retrieve_model(model_path, EMOTION_MODEL_MD5, EMOTION_MODEL_URL)

        self._session = ort.InferenceSession(str(model_path), providers=providers)
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name
        # input shape is [batch, 3, H, W]; derive the model's expected size (224 for b0, 260 for b2, ...)
        _, _, h, w = self._session.get_inputs()[0].shape
        self._img_size = (int(w), int(h))

    def predict(self, img_bgr: np.ndarray, bbox: np.ndarray) -> tuple[str, float]:
        """Return (emotion_label, softmax_confidence) for the face at bbox, or ("", 0.0) on failure."""
        try:
            h, w = img_bgr.shape[:2]
            x1, y1, x2, y2 = (int(v) for v in bbox)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return ("", 0.0)

            crop = img_bgr[y1:y2, x1:x2]
            rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, self._img_size).astype(np.float32) / 255.0
            normalized = (resized - _IMAGENET_MEAN) / _IMAGENET_STD
            tensor = normalized.transpose(2, 0, 1)[np.newaxis, ...].astype(np.float32)  # HWC -> 1,C,H,W

            logits = self._session.run([self._output_name], {self._input_name: tensor})[0][0]
            exp = np.exp(logits - np.max(logits))
            probs = exp / exp.sum()
            idx = int(np.argmax(probs))
            return (EMOTION_LABELS[idx], float(probs[idx]))
        except Exception:
            logger.exception("Error during emotion prediction")
            return ("", 0.0)


class FaceRecognitionService(BaseService):
    def __init__(self) -> None:
        super().__init__()
        self._app = None
        self._emotion: _EmotionClassifier | None = None
        self._known_faces: list[tuple[str, np.ndarray]] = []

    def start(self) -> None:
        super().start()

        if not appconfig.facerecognition.enabled:
            logger.info("FaceRecognitionService disabled via config.")
            super().disabled()
            return

        try:
            import onnxruntime as ort
            from insightface.app import FaceAnalysis

            if "CUDAExecutionProvider" in ort.get_available_providers():
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            else:
                providers = ["CPUExecutionProvider"]

            self._app = FaceAnalysis(
                name=appconfig.facerecognition.model_pack,
                providers=providers,
            )
            self._app.prepare(ctx_id=0, det_size=(640, 640))

        except Exception as exc:
            logger.error(f"Failed to initialize insightface, disabling service: {exc}")
            super().disabled()
            return

        if appconfig.facerecognition.predict_emotions:
            try:
                self._emotion = _EmotionClassifier(providers)
            except Exception as exc:
                # a missing/corrupt emotion model must not disable face recognition; {face_emotions} stays empty
                logger.error(f"Failed to initialize emotion classifier, continuing without emotions: {exc}")
                self._emotion = None

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

    def identify_faces(self, image_path: Path) -> list[RecognizedFace]:
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
            identified: list[RecognizedFace] = []
            identified_names: set[str] = set()

            for face in faces:
                query_emb = face.normed_embedding
                best_name: str | None = None
                best_score: float = -1.0

                for name, known_emb in self._known_faces:
                    score = float(np.dot(query_emb, known_emb))
                    if score > best_score:
                        best_score = score
                        best_name = name

                if best_name is not None and best_score >= threshold and best_name not in identified_names:
                    emotion, emotion_score = self._emotion.predict(img, face.bbox) if self._emotion else ("", 0.0)
                    identified.append(RecognizedFace(best_name, emotion, emotion_score))
                    identified_names.add(best_name)

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
