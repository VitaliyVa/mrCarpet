"""
Telegram bot entry — AI agent + future commands.

Фаза 1 notify: project.telegram_utils (outbound only).
Фаза 2 AI: project.telegram_agent.handler
"""
from project.telegram_agent.handler import handle_update, handle_update_async

__all__ = ["handle_update", "handle_update_async"]
