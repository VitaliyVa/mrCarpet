import io
import logging
import time
from pathlib import Path

import replicate
import requests
from django.conf import settings

from catalog.image_optimize import optimize_product_image
from catalog.services.replicate_color_match import (
    add_white_margin,
    crop_white_margins,
    match_rug_colors,
)
from catalog.services.replicate_prompt_options import GenerationOptions
from catalog.services.replicate_prompts import (
    PROMPT_VERSION,
    build_catalog_prompt,
    build_hover_prompt,
    build_scene_prompt,
)

logger = logging.getLogger("catalog.replicate")

PHASE_CATALOG = "catalog"
PHASE_HOVER = "hover"
PHASE_SCENE = "scene"
PREDICTION_TIMEOUT_SEC = 360
POLL_INTERVAL_SEC = 3

PHASE_CONFIG = {
    PHASE_CATALOG: {
        "label": "Каталог",
        "aspect_ratio": "2:3",
        "max_width": 500,
        "build_prompt": lambda opts: build_catalog_prompt(opts.catalog),
        "options_meta": lambda opts: opts.catalog.as_meta(),
    },
    PHASE_HOVER: {
        "label": "Hover",
        "aspect_ratio": "2:3",
        "max_width": 500,
        "build_prompt": lambda opts: build_hover_prompt(opts.catalog),
        "options_meta": lambda opts: opts.catalog.as_meta(),
    },
    PHASE_SCENE: {
        "label": "Сцена",
        "aspect_ratio": "4:3",
        "max_width": 1024,
        "build_prompt": lambda opts: build_scene_prompt(opts.scene),
        "options_meta": lambda opts: opts.scene.as_meta(),
    },
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

    def generate_phase(
        self,
        source_path: Path,
        phase: str,
        options: GenerationOptions | None = None,
    ) -> tuple[bytes, dict]:
        if phase not in PHASE_CONFIG:
            raise ReplicateGenerationError(f"Невідома фаза: {phase}")

        config = PHASE_CONFIG[phase]
        opts = options or GenerationOptions()
        prompt = config["build_prompt"](opts)
        aspect_ratio = config["aspect_ratio"]
        # Circle in 2:3 gets side-clipped; use square canvas for round catalog/hover.
        if (
            phase in (PHASE_CATALOG, PHASE_HOVER)
            and opts.catalog.rug_shape == "round"
        ):
            aspect_ratio = "1:1"
        max_width = config["max_width"]
        phase_label = config["label"]

        started = time.monotonic()
        source_bytes = source_path.read_bytes()
        source_name = source_path.name or "source.jpg"

        self.job_log.info(f"{phase_label}: відправлено на Replicate…")

        raw_bytes = self._run_and_download(
            source_bytes,
            source_name,
            prompt,
            phase_label,
            aspect_ratio,
        )
        if phase in (PHASE_CATALOG, PHASE_HOVER):
            self.job_log.info(f"{phase_label}: підгонка кольору під джерело…")
            raw_bytes = match_rug_colors(source_bytes, raw_bytes)
            self.job_log.info(f"{phase_label}: обрізка білих відступів…")
            raw_bytes = crop_white_margins(raw_bytes)
            # Circle bbox touches L/R midpoints — add a thin white ring so sides
            # don't look clipped in the catalog square.
            if opts.catalog.rug_shape == "round":
                self.job_log.info(f"{phase_label}: білий відступ для круга…")
                raw_bytes = add_white_margin(raw_bytes, margin_ratio=0.05)

        optimized = optimize_product_image(raw_bytes, max_width=max_width)

        duration = round(time.monotonic() - started, 1)
        self.job_log.ok(
            f"{phase_label}: готово за {duration} с ({len(optimized) // 1024} KB)"
        )

        meta = {
            "model": self.MODEL,
            "prompt_version": PROMPT_VERSION,
            "phase": phase,
            "aspect_ratio": aspect_ratio,
            "prompt_options": config["options_meta"](opts),
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
        phase_label: str,
        aspect_ratio: str,
    ) -> bytes:
        file_obj = io.BytesIO(source_bytes)
        file_obj.name = source_name

        prediction = self.client.predictions.create(
            model=self.MODEL,
            input={
                "prompt": prompt,
                "input_images": [file_obj],
                "aspect_ratio": aspect_ratio,
                "quality": "low",
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
