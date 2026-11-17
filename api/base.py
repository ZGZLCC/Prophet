"""Shared state, validation, paths, and task handling for the JS bridge."""

from __future__ import annotations

from concurrent.futures import Future
import os
from pathlib import Path
import sqlite3
import threading
import uuid
from typing import Any, Mapping

import background_jobs
import chat_analysis
import chat_export
from person_profile import analysis, storage
from process_runner import ProcessCancelled


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PATH_SETTING_NAMES = ("PROPHET_OUTPUT_DIR", "PROPHET_DATABASE_DIR")
MAX_SETTING_LENGTH = 2_000


class ApiBase:
    """Common context shared by the feature-specific bridge mixins."""

    def __init__(
        self,
        *,
        resource_root: str | Path | None = None,
        app_home: str | Path | None = None,
    ) -> None:
        self.resource_root = Path(resource_root or PROJECT_ROOT).resolve()
        default_home = Path(os.getenv("PROPHET_HOME", self.resource_root))
        self.app_home = Path(app_home or default_home).expanduser().resolve()
        self.env_path = self.app_home / ".env"
        self._window = None
        self._task_lock = threading.Lock()
        self._tasks: dict[str, tuple[str, Future[Any], threading.Event | None]] = {}

    def set_window(self, window: Any) -> None:
        self._window = window

    @staticmethod
    def _person_id(value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("人物编号无效。")
        if isinstance(value, float) and not value.is_integer():
            raise ValueError("人物编号无效。")
        try:
            person_id = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("人物编号无效。") from error
        if person_id < 1:
            raise ValueError("人物编号无效。")
        return person_id

    @staticmethod
    def _payload_text(
        payload: Mapping[str, Any],
        name: str,
        *,
        default: str = "",
        required: bool = False,
        max_length: int = MAX_SETTING_LENGTH,
    ) -> str:
        value = payload.get(name, default)
        if not isinstance(value, str):
            raise ValueError(f"{name}必须是文本。")
        if "\x00" in value:
            raise ValueError(f"{name}不能包含空字符。")
        value = value.strip()
        if required and not value:
            raise ValueError(f"{name}不能为空。")
        if len(value) > max_length:
            raise ValueError(f"{name}过长。")
        return value

    def _sentiment_db(self) -> Path:
        values = self._env_values()
        path = self._database_path(values, "APP_DB_PATH", "sentiment.db")
        storage.init_db(path)
        return path

    def _workspace(self, person_id: Any) -> dict[str, Any]:
        person_id = self._person_id(person_id)
        db_path = self._sentiment_db()
        person = storage.get_person(db_path, person_id)
        if person is None:
            raise ValueError(f"人物不存在：{person_id}")
        return {
            "person": person,
            "profile": storage.get_profile(db_path, person_id),
            "entries": storage.list_entries(db_path, person_id),
            "predictions": storage.list_predictions(db_path, person_id),
            "profile_revisions": storage.list_profile_revisions(db_path, person_id),
        }

    @staticmethod
    def _task_error(error: Exception) -> dict[str, str]:
        if isinstance(error, storage.DuplicateEntryError):
            code = "DUPLICATE_MATERIAL"
        elif isinstance(error, chat_export.ExportToolError):
            code = "CHAT_EXPORT_FAILED"
        elif isinstance(error, chat_analysis.ChatAnalysisError):
            code = "CHAT_ANALYSIS_FAILED"
        elif isinstance(error, analysis.ConfigurationError):
            code = "MODEL_NOT_CONFIGURED"
        elif isinstance(error, analysis.AnalysisError):
            code = "ANALYSIS_FAILED"
        elif isinstance(error, ValueError):
            code = "TASK_INPUT_INVALID"
        else:
            code = "TASK_FAILED"
        return {"code": code, "message": str(error) or "任务执行失败。"}

    def _submit_task(
        self,
        name: str,
        function: Any,
        /,
        *args: Any,
        cancel_event: threading.Event | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        task_id = uuid.uuid4().hex
        future = background_jobs.submit(function, *args, **kwargs)
        with self._task_lock:
            self._tasks[task_id] = (name, future, cancel_event)
        return {"task_id": task_id, "name": name, "status": "queued"}

    def _task_snapshot(self, task_id: str) -> dict[str, Any]:
        with self._task_lock:
            task = self._tasks.get(task_id)
        if task is None:
            raise KeyError("任务不存在或已过期。")
        name, future, _cancel_event = task
        if future.cancelled():
            return {"task_id": task_id, "name": name, "status": "cancelled"}
        if not future.done():
            return {
                "task_id": task_id,
                "name": name,
                "status": "running" if future.running() else "queued",
            }
        try:
            result = future.result()
        except Exception as error:  # noqa: BLE001 - bridge must return a stable envelope.
            if isinstance(error, ProcessCancelled):
                return {"task_id": task_id, "name": name, "status": "cancelled"}
            return {
                "task_id": task_id,
                "name": name,
                "status": "failed",
                "error": self._task_error(error),
            }
        return {
            "task_id": task_id,
            "name": name,
            "status": "succeeded",
            "result": result,
        }

    @staticmethod
    def _ok(data: Any) -> dict[str, Any]:
        return {"ok": True, "data": data}

    @staticmethod
    def _error(code: str, message: str) -> dict[str, Any]:
        return {"ok": False, "error": {"code": code, "message": message}}

    def _env_values(self) -> dict[str, str]:
        values = analysis.read_local_env(self.resource_root / ".env.example")
        values.update(analysis.read_local_env(self.env_path))
        for name in (*analysis.LLM_SETTING_NAMES, *PATH_SETTING_NAMES):
            if name in os.environ:
                values[name] = os.environ[name]
        return values

    def _setting_text(
        self,
        payload: Mapping[str, Any],
        name: str,
        *,
        default: str = "",
        required: bool = False,
    ) -> str:
        value = payload.get(name, default)
        if not isinstance(value, str):
            raise ValueError(f"{name}必须是文本。")
        value = value.strip()
        if "\x00" in value or "\n" in value or "\r" in value:
            raise ValueError(f"{name}不能包含换行或空字符。")
        if len(value) > MAX_SETTING_LENGTH:
            raise ValueError(f"{name}过长。")
        if required and not value:
            raise ValueError(f"{name}不能为空。")
        return value

    def _resolve_directory(self, value: str, label: str) -> Path:
        raw = value.strip().strip('"')
        if not raw:
            raise ValueError(f"请填写{label}。")
        if "\x00" in raw or "\n" in raw or "\r" in raw:
            raise ValueError(f"{label}不能包含换行或空字符。")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.app_home / path
        try:
            path = path.resolve()
        except OSError as error:
            raise ValueError(f"{label}不是有效路径。") from error
        if path.exists() and not path.is_dir():
            raise ValueError(f"{label}必须是文件夹。")
        return path

    def _resolve_file(self, value: Any, label: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}不能为空。")
        raw = value.strip().strip('"')
        if "\x00" in raw or "\n" in raw or "\r" in raw:
            raise ValueError(f"{label}不能包含换行或空字符。")
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.app_home / path
        try:
            path = path.resolve()
        except OSError as error:
            raise ValueError(f"{label}不是有效路径。") from error
        if not path.is_file():
            raise ValueError(f"找不到{label}：{path}")
        return path

    def _output_dir(self, values: Mapping[str, str]) -> Path:
        return self._resolve_directory(
            values.get("PROPHET_OUTPUT_DIR", "") or "output", "默认保存位置"
        )

    def _database_dir(self, values: Mapping[str, str]) -> Path:
        configured = values.get("PROPHET_DATABASE_DIR", "").strip()
        if configured:
            return self._resolve_directory(configured, "默认数据库位置")
        for name in ("APP_DB_PATH", "FORTUNE_DB_PATH"):
            configured = values.get(name, "").strip()
            if configured:
                path = Path(configured).expanduser()
                if not path.is_absolute():
                    path = self.app_home / path
                return path.resolve().parent
        return self.app_home / "data"

    def _database_path(
        self, values: Mapping[str, str], env_name: str, filename: str
    ) -> Path:
        if values.get("PROPHET_DATABASE_DIR", "").strip():
            return self._database_dir(values) / filename
        configured = values.get(env_name, "").strip()
        if configured:
            path = Path(configured).expanduser()
            return (path if path.is_absolute() else self.app_home / path).resolve()
        return self._database_dir(values) / filename

    @staticmethod
    def _mask_key(api_key: str) -> str:
        if not api_key:
            return ""
        return f"•••• {api_key[-4:]}" if len(api_key) >= 4 else "已配置"

    def get_task(self, task_id: Any) -> dict[str, Any]:
        try:
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("任务编号无效。")
            return self._ok(self._task_snapshot(task_id.strip()))
        except (KeyError, ValueError) as error:
            return self._error("TASK_READ_FAILED", str(error))

    def cancel_task(self, task_id: Any) -> dict[str, Any]:
        try:
            if not isinstance(task_id, str) or not task_id.strip():
                raise ValueError("任务编号无效。")
            task_id = task_id.strip()
            with self._task_lock:
                task = self._tasks.get(task_id)
            if task is None:
                raise KeyError("任务不存在或已过期。")
            cancel_event = task[2]
            requested = False
            if cancel_event is not None:
                cancel_event.set()
                requested = True
            requested = task[1].cancel() or requested
            return self._ok({"task_id": task_id, "cancelled": requested})
        except (KeyError, ValueError) as error:
            return self._error("TASK_CANCEL_FAILED", str(error))


__all__ = [
    "ApiBase",
    "MAX_SETTING_LENGTH",
    "PATH_SETTING_NAMES",
    "PROJECT_ROOT",
]
