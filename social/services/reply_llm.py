"""LLM-редактор відповідей на коменти клієнтів (HITL).

Сира відповідь оператора ("нє, нема") + оригінальний комент →
ввічлива фірмова відповідь українською. Модель: openai/gpt-4o-mini
через Replicate (той самий патерн, що blog/article_generate).
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

TEXT_MODEL = "openai/gpt-4o-mini"
LLM_TIMEOUT_SEC = 60

SYSTEM_PROMPT = """Ти — менеджер підтримки українського магазину килимів mr.Carpet (mrcarpet24.com).
Твоє завдання: перетворити СИРУ відповідь оператора на ввічливу фірмову відповідь клієнту в соцмережі.

Правила:
- Українська мова, тепло і з повагою, звертання на «ви».
- 1–3 короткі речення. Це відповідь на комент у соцмережі, не лист.
- Доречне привітання («Доброго дня!» / «Вітаємо!») — але без офіціозу.
- НЕ ВИГАДУЙ фактів: використовуй ЛИШЕ зміст сирої відповіді оператора.
  Якщо оператор написав «нема» — товару немає; не обіцяй поставок, якщо оператор цього не казав.
- Якщо товару немає / відповідь негативна — м'яко запропонуй подивитись інші моделі на сайті mrcarpet24.com.
- Максимум один емодзі, і лише якщо доречно.
- Без підпису (відповідь іде від імені магазину).
- Поверни ТІЛЬКИ текст відповіді, без лапок і пояснень."""


class ReplyLlmError(RuntimeError):
    pass


def generate_reply(
    *,
    platform: str,
    comment_text: str,
    operator_text: str,
    extra_instruction: str = "",
    variation: bool = False,
) -> str:
    token = (getattr(settings, "REPLICATE_API_TOKEN", None) or "").strip()
    if not token:
        raise ReplyLlmError("REPLICATE_API_TOKEN empty")

    try:
        import replicate
    except ImportError as exc:
        raise ReplyLlmError("replicate package not installed") from exc

    parts = [
        f"Платформа: {platform}",
        f"Комент клієнта: «{(comment_text or '').strip()[:800]}»",
        f"Сира відповідь оператора: «{(operator_text or '').strip()[:800]}»",
    ]
    if extra_instruction:
        parts.append(f"Додаткова інструкція оператора: {extra_instruction.strip()[:400]}")
    if variation:
        parts.append("Згенеруй ІНШИЙ варіант формулювання, ніж очевидний перший.")
    parts.append("Напиши фінальну відповідь клієнту:")
    user_prompt = "\n".join(parts)

    client = replicate.Client(api_token=token)
    try:
        output = client.run(
            TEXT_MODEL,
            input={
                "system_prompt": SYSTEM_PROMPT,
                "prompt": user_prompt,
                "temperature": 0.9 if variation else 0.6,
                "max_completion_tokens": 300,
            },
        )
    except Exception as exc:
        raise ReplyLlmError(f"LLM call failed: {exc}") from exc

    if isinstance(output, list):
        text = "".join(str(chunk) for chunk in output)
    else:
        text = str(output)
    text = text.strip().strip('"').strip()
    if not text:
        raise ReplyLlmError("LLM returned empty reply")
    return text[:1500]
