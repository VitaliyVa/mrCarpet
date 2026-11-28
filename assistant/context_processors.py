def assistant(request):
    """`assistant_enabled` for _base.html: load the chat widget only when the
    bot is switched on and has a key. Admin pages never get it."""
    if request.path.startswith("/admin"):
        return {"assistant_enabled": False}
    try:
        from .models import AssistantSettings

        return {"assistant_enabled": AssistantSettings.load().is_live}
    except Exception:
        return {"assistant_enabled": False}
