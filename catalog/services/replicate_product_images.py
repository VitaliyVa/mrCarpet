import io
import logging
import time
from pathlib import Path

import replicate
import requests
from django.conf import settings

from catalog.image_optimize import optimize_product_image
from catalog.services.replicate_prompts import (
    PROMPT_CATALOG_IMAGE,
    PROMPT_HOVER_IMAGE,
    PROMPT_VERSION,
)

logger = logging.getLogger("catalog.replicate")

PHASE_CATALOG = "catalog"
PHASE_HOVER = "hover"
PREDICTION_TIMEOUT_SEC = 360
POLL_INTERVAL_SEC = 3
ASPECT_RATIO = "2:3"

PROMPTS = {
    PHASE_CATALOG: PROMPT_CATALOG_IMAGE,
    PHASE_HOVER: PROMPT_HOVER_IMAGE,
}


class ReplicateGenerationError(Exception):
    pass


class ReplicateJobLog:
    def __init__(self):
        self.entries: list[dict] = []

    def _add(self, level: str, message: str) -> None:
        self.entries.append({"level": level, "text": message})
        if level == "error":
            logger.error(message)
        else:
            logger.info(message)

    def info(self, message: str) -> None:
        self._add("info", message)

    def ok(self, message: str) -> None:
        self._add("ok", message)

    def error(self, message: str) -> None:
        self._add("error", message)


class ReplicateProductImageService:
    MODEL = "openai/gpt-image-2"

    def __init__(self):
        token = settings.REPLICATE_API_TOKEN
        if not token:
            raise ReplicateGenerationError(
                "REPLICATE_API_TOKEN не налаштовано. Додайте токен у .env"
            )
        self.client = replicate.Client(api_token=token)
        self.job_log = ReplicateJobLog()

    def generate_phase(self, source_path: Path, phase: str) -> tuple[bytes, dict]:
        if phase not in PROMPTS:
            raise ReplicateGenerationError(f"Невідома фаза: {phase}")

        started = time.monotonic()
        source_bytes = source_path.read_bytes()
        source_name = source_path.name or "source.jpg"

        phase_label = "Каталог" if phase == PHASE_CATALOG else "Hover"
        self.job_log.info(f"{phase_label}: відправлено на Replicate…")

        raw_bytes = self._run_and_download(
            source_bytes,
            source_name,
            PROMPTS[phase],
            phase,
            phase_label,
        )
        optimized = optimize_product_image(raw_bytes)

        duration = round(time.monotonic() - started, 1)
        self.job_log.ok(f"{phase_label}: готово за {duration} с ({len(optimized) // 1024} KB)")

        meta = {
            "model": self.MODEL,
            "prompt_version": PROMPT_VERSION,
            "phase": phase,
            "aspect_ratio": ASPECT_RATIO,
            "duration_sec": duration,
            "output_size_kb": len(optimized) // 1024,
            "logs": self.job_log.entries,
        }
        return optimized, meta

    def _run_and_download(
        self,
        source_bytes: bytes,
        source_name: str,
        prompt: str,
        phase: str,
        phase_label: str,
    ) -> bytes:
        file_obj = io.BytesIO(source_bytes)
        file_obj.name = source_name

        prediction = self.client.predictions.create(
            model=self.MODEL,
            input={
                "prompt": prompt,
                "input_images": [file_obj],
                "aspect_ratio": ASPECT_RATIO,
                "quality": "high",
                "output_format": "webp",
                "output_compression": 90,
                "background": "opaque",
                "number_of_images": 1,
            },
        )
        logger.info("%s: prediction id=%s", phase_label, prediction.id)

        prediction = self._poll_prediction(prediction, phase_label)

        if prediction.status != "succeeded":
            error = prediction.error or "Невідома помилка Replicate"
            self.job_log.error(f"{phase_label}: {error}")
            raise ReplicateGenerationError(error)

        output = prediction.output
        if not output:
            raise ReplicateGenerationError("Replicate не повернув зображення")

        url = output[0] if isinstance(output, list) else output
        response = requests.get(url, timeout=120)
        response.raise_for_status()
        return response.content

    def _poll_prediction(self, prediction, phase_label: str):
        deadline = time.monotonic() + PREDICTION_TIMEOUT_SEC
        last_status = None
        processing_logged = False

        while prediction.status not in ("succeeded", "failed", "canceled"):
            if time.monotonic() > deadline:
                self.job_log.error(f"{phase_label}: таймаут {PREDICTION_TIMEOUT_SEC} с")
                try:
                    prediction.cancel()
                except Exception as exc:
                    logger.error("Cancel failed: %s", exc)
                raise ReplicateGenerationError(
                    f"Таймаут очікування Replicate ({PREDICTION_TIMEOUT_SEC} с). "
                    f"Prediction id: {prediction.id}"
                )

            if prediction.status != last_status:
                if prediction.status == "processing" and not processing_logged:
                    self.job_log.info(f"{phase_label}: Replicate обробляє…")
                    processing_logged = True
                last_status = prediction.status
                logger.info("%s: status=%s", phase_label, prediction.status)

            time.sleep(POLL_INTERVAL_SEC)
            prediction.reload()

        return prediction
