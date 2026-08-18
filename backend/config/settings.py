"""Application settings loaded from environment variables (no magic numbers in code)."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from utils.logging import get_logger

logger = get_logger(__name__)


class Settings(BaseSettings):
    """All runtime configuration comes from ENV / .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Application
    app_name: str = "Rack Insight"
    app_version: str = "1.5.0"
    debug: bool = False
    api_prefix: str = "/api"
    cors_origins: str = "http://localhost:5173,http://localhost:3000,http://localhost"

    # Database
    database_url: str = "postgresql+asyncpg://rackinsight:rackinsight@postgres:5432/rackinsight"

    # Redis
    redis_url: str = "redis://redis:6379/0"
    cache_ttl_seconds: int = 600

    # Auth / JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Credential encryption (Fernet key, 32 url-safe base64 bytes)
    encryption_key: str = "0RPYS0nOu5f5xkbXi3wYlLYasNci4RMOtayEqUKmyNI="

    # Default admin bootstrap
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123!"

    # Collector
    collector_timeout_seconds: int = 10
    collector_retry_count: int = 3
    collector_version: str = "1.0.0"

    # Scheduler
    scheduler_enabled: bool = True
    scheduler_interval_seconds: int = 1800

    # Plugins (Plugin Architecture Foundation).
    # Config-based registration is air-gap friendly: provide a JSON array either
    # inline (PLUGINS_CONFIG) or via a file/ConfigMap (PLUGINS_CONFIG_FILE), e.g.
    #   [{"name":"example-plugin","endpoint":"http://example-plugin:8080",
    #     "enabled":true,"display_name":"Example Plugin"}]
    plugins_config: str = ""
    plugins_config_file: str = ""
    plugin_health_enabled: bool = True
    plugin_health_interval_seconds: int = 60
    plugin_request_timeout_seconds: int = 5

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@dataclass(frozen=True)
class PluginConfig:
    name: str
    endpoint: str
    enabled: bool = True
    display_name: str | None = None


def _parse_plugin_configs(raw: str, source: str) -> list[PluginConfig]:
    raw = raw.strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Invalid plugin config JSON (%s): %s", source, exc)
        return []
    if not isinstance(data, list):
        logger.error("Plugin config (%s) must be a JSON array", source)
        return []
    configs: list[PluginConfig] = []
    for entry in data:
        if not isinstance(entry, dict) or not entry.get("name") or not entry.get("endpoint"):
            logger.error("Skipping malformed plugin config entry: %r", entry)
            continue
        configs.append(
            PluginConfig(
                name=str(entry["name"]),
                endpoint=str(entry["endpoint"]),
                enabled=bool(entry.get("enabled", True)),
                display_name=entry.get("display_name") or entry.get("displayName"),
            )
        )
    return configs


def load_plugin_configs() -> list[PluginConfig]:
    """Declared plugins from PLUGINS_CONFIG (inline JSON) and/or
    PLUGINS_CONFIG_FILE (path to a JSON file / ConfigMap). Malformed entries are
    skipped with a log line and never crash startup (failure isolation)."""
    settings = get_settings()
    configs: dict[str, PluginConfig] = {}
    for cfg in _parse_plugin_configs(settings.plugins_config, "PLUGINS_CONFIG"):
        configs[cfg.name] = cfg
    if settings.plugins_config_file:
        try:
            raw = Path(settings.plugins_config_file).read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Cannot read PLUGINS_CONFIG_FILE: %s", exc)
        else:
            for cfg in _parse_plugin_configs(raw, "PLUGINS_CONFIG_FILE"):
                configs[cfg.name] = cfg
    return list(configs.values())


@lru_cache
def get_settings() -> Settings:
    return Settings()
