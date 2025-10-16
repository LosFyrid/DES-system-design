"""
Configuration management for Web Backend

Loads configuration from environment variables and agent config files.
"""

import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class WebConfig(BaseSettings):
    """Web backend configuration"""

    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = True

    # CORS Configuration
    cors_origins: str = "http://localhost:3000,http://localhost:3001"

    # Agent Configuration Paths
    agent_config_path: str = "../agent/config/reasoningbank_config.yaml"
    recommendations_path: str = "../../data/recommendations"
    memory_path: str = "../../data/memory"

    # Logging
    log_level: str = "INFO"

    # LLM Configuration (if not using agent config)
    dashscope_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string"""
        return [origin.strip() for origin in self.cors_origins.split(",")]

    def get_agent_config_path(self) -> Path:
        """Get absolute path to agent config file"""
        base_path = Path(__file__).parent
        return (base_path / self.agent_config_path).resolve()

    def get_recommendations_dir(self) -> Path:
        """Get absolute path to recommendations directory"""
        base_path = Path(__file__).parent
        return (base_path / self.recommendations_path).resolve()

    def get_memory_dir(self) -> Path:
        """Get absolute path to memory directory"""
        base_path = Path(__file__).parent
        return (base_path / self.memory_path).resolve()


# Global config instance
_config: Optional[WebConfig] = None


def get_web_config() -> WebConfig:
    """Get web config singleton"""
    global _config
    if _config is None:
        _config = WebConfig()
    return _config
