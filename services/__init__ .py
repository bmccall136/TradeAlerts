# services/__init__.py
# Ensure LiveBroker gets the ATT-first helpers before anything else imports it.
try:
    from . import broker_patch  # noqa: F401
except Exception:
    # Keep imports from breaking if patch fails; your logs will show the error.
    pass
