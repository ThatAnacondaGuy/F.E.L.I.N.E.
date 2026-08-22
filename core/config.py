"""Configuration system."""

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
import toml
from typing import Dict, Any

class Config(BaseSettings):
    """System configuration using pydantic-settings."""
    
    system: Dict[str, Any] = {}
    user: Dict[str, Any] = {}
    models: Dict[str, Any] = {}
    server: Dict[str, Any] = {}
    security: Dict[str, Any] = {}
    
    model_config = SettingsConfigDict(env_prefix="MEOW_OS_", env_nested_delimiter="__")
    
    _instance = None
    
    @classmethod
    def load(cls, configs_dir: str) -> "Config":
        """Load configuration from TOML files."""
        if cls._instance is None:
            config_data = {}
            configs_path = Path(configs_dir)
            
            if configs_path.exists():
                for toml_file in configs_path.glob("*.toml"):
                    with open(toml_file, "r") as f:
                        data = toml.load(f)
                        if toml_file.name == "default.toml":
                            config_data.update(data)
                        else:
                            config_data[toml_file.stem] = data
            
            cls._instance = cls(**config_data)
        return cls._instance

def get_config() -> Config:
    """Get the singleton configuration instance."""
    # Assuming standard path relative to this file's intended location
    configs_dir = Path(__file__).parent.parent / "configs"
    return Config.load(str(configs_dir))
