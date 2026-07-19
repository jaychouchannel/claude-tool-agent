"""Configuration: load .env, expose settings."""
import os
import warnings

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    warnings.warn("python-dotenv not installed; .env file will NOT be loaded")


def get_default_api_key() -> str | None:
    """Return API key from environment, if set. UI may override per-request."""
    return os.environ.get("ANTHROPIC_API_KEY")


def get_default_model() -> str:
    """Default Claude model. Override with ANTHROPIC_MODEL env var."""
    return os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
