"""Settings, local health, and database-path operations exposed to the UI."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from person_profile import analysis
import platform_support

APP_VERSION = "1.0.0"

TIME_ZONES = {
    "Asia/Shanghai": "北京",
    "Asia/Hong_Kong": "香港",
    "Asia/Singapore": "新加坡",
    "Asia/Tokyo": "东京",
    "Europe/London": "伦敦",
    "Europe/Paris": "巴黎",
    "America/New_York": "纽约",
    "America/Los_Angeles": "洛杉矶",
    "Australia/Sydney": "悉尼",
    "UTC": "协调世界时（UTC）",
}


class SettingsApiMixin:
    def _public_settings(self, values: Mapping[str, str]) -> dict[str, Any]:
        api_key = values.get("LLM_API_KEY", "")
        provider = values.get("LLM_PROVIDER", "") or analysis.SUPPORTED_LLM_PROVIDER
        model = values.get("LLM_MODEL", "")
        return {
            "theme": values.get("PROPHET_THEME", "system")
            if values.get("PROPHET_THEME", "system") in {"system", "light", "dark"}
            else "system",
            "timezone": values.get("PROPHET_TIMEZONE", "Asia/Shanghai")
            if values.get("PROPHET_TIMEZONE", "Asia/Shanghai") in TIME_ZONES
            else "Asia/Shanghai",
            "provider": provider,
            "base_url": values.get("LLM_BASE_URL", ""),
            "model": model,
            "api_key_configured": bool(api_key),
            "api_key_masked": self._mask_key(api_key),
            "llm_configured": bool(
                model
                and provider in analysis.SUPPORTED_LLM_PROVIDERS
                and (provider == "ollama" or api_key)
            ),
            "output_dir": str(self._output_dir(values)),
            "database_dir": str(self._database_dir(values)),
            "env_path": str(self.env_path),
        }

    def get_app_info(self) -> dict[str, Any]:
        return self._ok(
            {
                "name": "Prophet",
                "version": APP_VERSION,
                "platform": platform_support.platform_tag(),
                "chat_export": platform_support.CHAT_EXPORT_SUPPORTED,
                "shell": "pywebview",
                "local_only": True,
                "streamlit": False,
                "http_service": False,
            }
        )

    def get_settings(self) -> dict[str, Any]:
        try:
            return self._ok(self._public_settings(self._env_values()))
        except (OSError, ValueError) as error:
            return self._error("SETTINGS_READ_FAILED", str(error))

    def health_check(self) -> dict[str, Any]:
        try:
            values = self._env_values()
            databases = []
            for label, env_name, filename in (
                ("情绪数据库", "APP_DB_PATH", "sentiment.db"),
                ("赛博算命数据库", "FORTUNE_DB_PATH", "fortune.db"),
            ):
                path = self._database_path(values, env_name, filename)
                item = {"name": label, "path": str(path), "status": "empty"}
                if path.is_file():
                    try:
                        with sqlite3.connect(path) as connection:
                            result = connection.execute("PRAGMA quick_check").fetchone()[0]
                        item["status"] = "ok" if result == "ok" else "error"
                    except (OSError, sqlite3.Error):
                        item["status"] = "error"
                databases.append(item)
            statuses = {item["status"] for item in databases}
            status = "error" if "error" in statuses else "ok"
            return self._ok(
                {
                    "status": status,
                    "streamlit": False,
                    "http_service": False,
                    "database_summary": "本地数据库存在异常" if status == "error" else "本地数据库状态正常",
                    "databases": databases,
                }
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("HEALTH_CHECK_FAILED", str(error))

    def save_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(payload, Mapping):
                raise ValueError("设置格式无效。")
            current = self._env_values()
            provider = self._setting_text(
                payload,
                "provider",
                default=current.get("LLM_PROVIDER", "") or analysis.SUPPORTED_LLM_PROVIDER,
                required=True,
            )
            base_url = self._setting_text(
                payload, "base_url", default=current.get("LLM_BASE_URL", "")
            )
            model = self._setting_text(
                payload, "model", default=current.get("LLM_MODEL", ""), required=True
            )
            api_key = self._setting_text(
                payload, "api_key", default=current.get("LLM_API_KEY", "")
            ) or current.get("LLM_API_KEY", "")
            if provider not in analysis.SUPPORTED_LLM_PROVIDERS:
                raise ValueError("接口协议不受支持。")
            if provider != "ollama" and not api_key:
                raise ValueError("非 Ollama 接口还需要 API Key。")
            settings = {
                "LLM_PROVIDER": provider,
                "LLM_BASE_URL": base_url,
                "LLM_API_KEY": api_key,
                "LLM_MODEL": model,
            }
            analysis.save_local_env(
                self.env_path, settings, template=self.resource_root / ".env.example"
            )
            os.environ.update(settings)
            return self.get_settings()
        except (OSError, ValueError) as error:
            return self._error("SETTINGS_SAVE_FAILED", str(error))

    def save_appearance_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(payload, Mapping):
                raise ValueError("外观设置格式无效。")
            theme = self._setting_text(payload, "theme", required=True)
            timezone = self._setting_text(
                payload,
                "timezone",
                default=self._env_values().get("PROPHET_TIMEZONE", "Asia/Shanghai"),
                required=True,
            )
            if theme not in {"system", "light", "dark"}:
                raise ValueError("主题设置无效。")
            if timezone not in TIME_ZONES:
                raise ValueError("时区设置无效。")
            analysis.save_local_env(
                self.env_path,
                {"PROPHET_THEME": theme, "PROPHET_TIMEZONE": timezone},
                template=self.resource_root / ".env.example",
            )
            return self.get_settings()
        except (OSError, ValueError) as error:
            return self._error("APPEARANCE_SETTINGS_SAVE_FAILED", str(error))

    @staticmethod
    def _sync_database(source: Path, destination: Path) -> None:
        source, destination = source.resolve(), destination.resolve()
        if not source.is_file() or source == destination:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source) as source_connection, sqlite3.connect(
            destination
        ) as destination_connection:
            source_connection.backup(destination_connection)

    def save_path_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            if not isinstance(payload, Mapping):
                raise ValueError("路径设置格式无效。")
            current = self._env_values()
            output_dir = self._resolve_directory(
                self._setting_text(
                    payload,
                    "output_dir",
                    default=str(self._output_dir(current)),
                    required=True,
                ),
                "默认保存位置",
            )
            database_dir = self._resolve_directory(
                self._setting_text(
                    payload,
                    "database_dir",
                    default=str(self._database_dir(current)),
                    required=True,
                ),
                "默认数据库位置",
            )
            new_paths = (database_dir / "sentiment.db", database_dir / "fortune.db")
            for env_name, filename, destination in zip(
                ("APP_DB_PATH", "FORTUNE_DB_PATH"),
                ("sentiment.db", "fortune.db"),
                new_paths,
            ):
                self._sync_database(
                    self._database_path(current, env_name, filename), destination
                )
            settings = {
                "PROPHET_OUTPUT_DIR": str(output_dir),
                "PROPHET_DATABASE_DIR": str(database_dir),
                "APP_DB_PATH": str(new_paths[0]),
                "FORTUNE_DB_PATH": str(new_paths[1]),
            }
            analysis.save_local_env(
                self.env_path, settings, template=self.resource_root / ".env.example"
            )
            os.environ.update(settings)
            return self.get_settings()
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("PATH_SETTINGS_SAVE_FAILED", str(error))
