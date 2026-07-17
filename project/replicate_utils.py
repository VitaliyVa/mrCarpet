"""Shared Replicate helpers (poll + JSON extract) for SEO/blog generators."""

from __future__ import annotations

import json
import re
import time
from typing import Any, Type


def extract_json_object(text: str, *, error_cls: Type[Exception]) -> dict[str, Any]:
    """Parse model output into a JSON object; raise error_cls on failure."""
    raw = (text or "").strip()
    if not raw:
        raise error_cls("Порожня відповідь моделі")

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, re.I)
    if fence:
        raw = fence.group(1).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            raise error_cls("Не вдалося розпарсити JSON з відповіді моделі")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise error_cls("Невалідний JSON у відповіді моделі") from exc

    if not isinstance(data, dict):
        raise error_cls("Очікувався JSON-об'єкт")
    return data


def poll_prediction(
    prediction,
    *,
    timeout_sec: float,
    poll_interval_sec: float = 2.0,
    error_cls: Type[Exception] = RuntimeError,
    label: str = "prediction",
):
    """
    Wait until prediction reaches a terminal status.
    Cancels on timeout when possible.
    """
    terminal = ("succeeded", "failed", "canceled")
    deadline = time.monotonic() + timeout_sec

    while prediction.status not in terminal:
        if time.monotonic() > deadline:
            try:
                prediction.cancel()
            except Exception:
                pass
            raise error_cls(
                f"Таймаут {label} ({int(timeout_sec)} с). "
                f"Prediction id: {getattr(prediction, 'id', '?')}"
            )
        time.sleep(poll_interval_sec)
        prediction.reload()

    return prediction
