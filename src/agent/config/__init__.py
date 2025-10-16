"""
Configuration management for ReasoningBank Agent.

Usage:
    from agent.config import get_config

    config = get_config()
    llm_config = config.get_llm_config()
    model = config.get("llm.model")
"""

from .config_loader import ConfigLoader, get_config

__all__ = ["ConfigLoader", "get_config"]
