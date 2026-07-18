"""Replicate LLM loop (ReAct-lite, JSON plans)."""
from __future__ import annotations

import json
import logging
from typing import Any

import replicate
from django.conf import settings as django_settings

from project.replicate_utils import extract_json_object, poll_prediction

from .tools import tool_specs_for_prompt

logger = logging.getLogger(__name__)

PREDICTION_TIMEOUT_SEC = 90
POLL_INTERVAL_SEC = 1.5
MAX_TOOL_ROUNDS = 2
MAX_TOOLS_PER_TURN = 3


class AgentLlmError(Exception):
    pass


SYSTEM_PROMPT = """Ти — оператор магазину mr.Carpet у Telegram-групі команди.
Відповідай ТІЛЬКИ українською, коротко і по суті.
Статуси замовлень у відповідях людям — українською (напр. «Виконано»), код у дужках ок.
НІКОЛИ не вигадуй цифри зі складу/замовлень — тільки з TOOL_RESULTS.
ЗАБОРОНЕНО писати "виконую команду" текстом — для даних завжди type=tool.
У відповідях людям НЕ називай внутрішні імена tools (count_orders тощо).
WRITE tools не виконуються одразу: type=write або type=tools, система попросить ✅.

Контекст:
- Номер замовлення бери з USER / HISTORY / REPLY_CONTEXT (повідомлення, на яке відповіли).
- Не плутай склад (change_stock_quantity) зі статусом замовлення.
- Якщо просять «зміни статус І напиши лист» — ОБОВ'ЯЗКОВО обидві write-дії в одному
  type=tools.calls (set_order_status + send_order_email). subject/body українською.
- Якщо номер замовлення невідомий — type=reply з коротким уточненням, не вигадуй.

Повертай ЛИШЕ один JSON-об'єкт (без markdown fence), рівно один з форматів:
{"type":"reply","text":"..."}
{"type":"tool","name":"TOOL_NAME","args":{...}}
{"type":"write","name":"WRITE_TOOL","args":{...}}
{"type":"tools","calls":[{"name":"...","args":{...}}]}

Доступні tools:
"""


def _client():
    token = django_settings.REPLICATE_API_TOKEN
    if not token:
        raise AgentLlmError("REPLICATE_API_TOKEN не налаштовано")
    return replicate.Client(api_token=token)


def _flatten_output(output) -> str:
    if isinstance(output, list):
        return "".join(str(x) for x in output)
    return str(output or "").strip()


def run_model(model: str, system_prompt: str, prompt: str, *, temperature=0.2) -> str:
    client = _client()
    # Different Llama ports accept slightly different input keys
    combined = f"{system_prompt}\n\n{prompt}"
    input_variants = [
        {
            "system_prompt": system_prompt,
            "prompt": prompt,
            "temperature": temperature,
            "max_tokens": 800,
        },
        {
            "prompt": combined,
            "temperature": temperature,
            "max_new_tokens": 800,
        },
        {
            "prompt": combined,
            "max_tokens": 800,
        },
    ]
    last_err = None
    for inp in input_variants:
        try:
            prediction = client.predictions.create(model=model, input=inp)
            prediction = poll_prediction(
                prediction,
                timeout_sec=PREDICTION_TIMEOUT_SEC,
                poll_interval_sec=POLL_INTERVAL_SEC,
                error_cls=AgentLlmError,
                label="telegram-agent",
            )
            if prediction.status != "succeeded":
                last_err = prediction.error or "Replicate failed"
                # invalid input → try next shape
                if prediction.status == "failed" and last_err and "input" in str(last_err).lower():
                    continue
                raise AgentLlmError(last_err)
            text = _flatten_output(prediction.output)
            if not text:
                raise AgentLlmError("Порожній output від моделі")
            return text
        except AgentLlmError as exc:
            last_err = str(exc)
            continue
    raise AgentLlmError(last_err or "Replicate failed")


def parse_plan(raw: str) -> dict[str, Any]:
    data = extract_json_object(raw, error_cls=AgentLlmError)
    if "type" not in data:
        # tolerate {"text": "..."}
        if "text" in data:
            return {"type": "reply", "text": data["text"]}
        raise AgentLlmError("JSON без type")
    return data


def build_user_prompt(
    *,
    summary: str,
    history: list[dict],
    user_text: str,
    tool_results: list[dict] | None = None,
    reply_context: str = "",
) -> str:
    parts = []
    if summary:
        parts.append(f"SUMMARY:\n{summary}")
    if history:
        lines = []
        for h in history:
            lines.append(f"{h['role'].upper()}: {h['content']}")
        parts.append("HISTORY:\n" + "\n".join(lines))
    if reply_context:
        parts.append(f"REPLY_CONTEXT (повідомлення, на яке відповідає USER):\n{reply_context}")
    parts.append(f"USER:\n{user_text}")
    if tool_results:
        parts.append(
            "TOOL_RESULTS:\n" + json.dumps(tool_results, ensure_ascii=False, default=str)
        )
        parts.append(
            "На основі TOOL_RESULTS дай фінальну відповідь JSON type=reply "
            "українською (статуси — українськими назвами) "
            "або ще один READ tool якщо даних бракує."
        )
    else:
        parts.append("Дай JSON plan (reply / tool / write / tools).")
    return "\n\n".join(parts)


def plan_once(
    model: str,
    *,
    summary: str,
    history: list[dict],
    user_text: str,
    tool_results: list[dict] | None = None,
    reply_context: str = "",
    retry: bool = True,
) -> dict[str, Any]:
    system = SYSTEM_PROMPT + "\n" + tool_specs_for_prompt()
    prompt = build_user_prompt(
        summary=summary,
        history=history,
        user_text=user_text,
        tool_results=tool_results,
        reply_context=reply_context,
    )
    try:
        raw = run_model(model, system, prompt)
        return parse_plan(raw)
    except AgentLlmError:
        if not retry:
            raise
        # one retry with stricter hint
        prompt2 = prompt + "\n\nIMPORTANT: output ONLY valid minified JSON object."
        raw = run_model(model, system, prompt2, temperature=0.1)
        return parse_plan(raw)


def summarize(model: str, old_summary: str, recent: str) -> str:
    system = "Стисни діалог українською до 5-8 речень фактів про магазин/замовлення. Лише текст."
    prompt = f"OLD_SUMMARY:\n{old_summary}\n\nRECENT:\n{recent}\n\nNEW_SUMMARY:"
    try:
        return run_model(model, system, prompt, temperature=0.2)[:2000]
    except Exception as exc:
        logger.warning("summarize failed: %s", exc)
        return old_summary
