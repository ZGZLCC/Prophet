"""赛博算命页面的本地 API 适配层。"""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

import fortune_app
from fortune import knowledge as fortune_knowledge
from fortune import storage as fortune_storage


class FortuneApiMixin:
    """赛博算命起盘、解读、档案和复盘操作。"""

    def _fortune_db(self) -> Path:
        values = self._env_values()
        path = self._database_path(values, "FORTUNE_DB_PATH", "fortune.db")
        fortune_storage.init_db(path)
        return path

    @staticmethod
    def _fortune_id(value: Any, label: str = "记录编号") -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label}无效。")
        result = value.strip()
        if "\x00" in result or "\n" in result or "\r" in result or len(result) > 100:
            raise ValueError(f"{label}无效。")
        return result

    def _fortune_reading(self, reading_id: Any) -> dict[str, Any]:
        reading_id = self._fortune_id(reading_id)
        for item in fortune_storage.list_readings(self._fortune_db()):
            if item.get("id") == reading_id:
                return item
        raise ValueError("所选盘面不存在。")

    def _fortune_payload_with_profile(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("起盘参数格式无效。")
        values = payload.get("values", {})
        if not isinstance(values, Mapping):
            raise ValueError("术式输入格式无效。")
        resolved = dict(payload)
        values = dict(values)
        profile_id = values.get("profileId", payload.get("profile_id"))
        if profile_id not in (None, ""):
            profile_id = self._fortune_id(profile_id, "命主档案编号")
            profiles = fortune_storage.list_profiles(self._fortune_db())
            profile = next((item for item in profiles if item.get("id") == profile_id), None)
            if profile is None:
                raise ValueError("所选命主档案不存在。")
            values.update(
                {
                    "profileId": profile_id,
                    "displayName": profile.get("display_name", ""),
                    "birthAt": profile.get("birth_at"),
                    "gender": profile.get("gender", "unspecified"),
                    "luckDirection": profile.get("luck_direction", "auto-gender-year-stem"),
                }
            )
        resolved["values"] = values
        return resolved

    def get_fortune_workspace(self) -> dict[str, Any]:
        try:
            db_path = self._fortune_db()
            return self._ok(
                {
                    "engines": fortune_app.ENGINE_LABELS,
                    "policies": fortune_app.POLICIES,
                    "categories": fortune_app.CATEGORIES,
                    "genders": fortune_app.GENDERS,
                    "luck_directions": fortune_app.LUCK_DIRECTIONS,
                    "meihua_methods": fortune_app.MEIHUA_METHODS,
                    "profiles": fortune_storage.list_profiles(db_path),
                    "readings": fortune_storage.list_readings(db_path),
                    "claims": fortune_storage.list_claims(db_path),
                    "database": fortune_storage.verify_database(db_path),
                }
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_WORKSPACE_READ_FAILED", str(error))

    def calculate_fortune(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            resolved = self._fortune_payload_with_profile(payload)
            return self._ok(fortune_app.calculate_and_save(self._fortune_db(), resolved))
        except (OSError, ValueError, KeyError, NotImplementedError, sqlite3.Error) as error:
            return self._error("FORTUNE_CALCULATION_FAILED", str(error))

    def delete_fortune_reading(
        self, reading_id: Any, confirmed: Any = False
    ) -> dict[str, Any]:
        try:
            reading_id = self._fortune_id(reading_id)
            if confirmed is not True:
                raise ValueError("删除盘面前请先确认。")
            deleted = fortune_storage.delete_reading(self._fortune_db(), reading_id)
            return self._ok({"deleted": deleted, "reading_id": reading_id})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_READING_DELETE_FAILED", str(error))

    def export_fortune_reading(
        self, reading_id: Any, directory: Any = ""
    ) -> dict[str, Any]:
        try:
            item = self._fortune_reading(reading_id)
            if not isinstance(directory, str):
                raise ValueError("保存位置无效。")
            target = self._resolve_directory(
                directory.strip() or str(self._output_dir(self._env_values())), "保存位置"
            )
            path = fortune_app.export_reading_report(item, target)
            return self._ok(
                {
                    "reading_id": item["id"],
                    "path": str(path.resolve()),
                    "size_bytes": path.stat().st_size,
                }
            )
        except (OSError, ValueError, KeyError) as error:
            return self._error("FORTUNE_READING_EXPORT_FAILED", str(error))

    @staticmethod
    def _run_fortune_interpretation(arguments: Mapping[str, Any]) -> dict[str, Any]:
        content = fortune_knowledge.interpret(
            str(arguments["question"]),
            [arguments["facts"]],
            engine=str(arguments["engine"]),
            values=arguments["values"],
            category=str(arguments["category"]),
        )
        fortune_storage.save_interpretation(
            arguments["db_path"],
            session_id=str(arguments["reading_id"]),
            content_markdown=content,
        )
        return {"reading_id": arguments["reading_id"], "content": content}

    def start_fortune_interpretation(self, reading_id: Any) -> dict[str, Any]:
        try:
            item = self._fortune_reading(reading_id)
            run = item.get("runs", [{}])[0]
            facts = run.get("facts", {})
            task = self._submit_task(
                "fortune-interpretation",
                self._run_fortune_interpretation,
                {
                    "db_path": str(self._fortune_db()),
                    "reading_id": item["id"],
                    "question": item.get("question", "未命名占测"),
                    "engine": run.get("engine_id", ""),
                    "values": run.get("input", {}),
                    "category": item.get("category") or "other",
                    "facts": facts,
                },
            )
            return self._ok(task)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("FORTUNE_INTERPRETATION_START_FAILED", str(error))

    def get_fortune_agent_prompt(self, reading_id: Any) -> dict[str, Any]:
        try:
            item = self._fortune_reading(reading_id)
            run = item.get("runs", [{}])[0]
            prompt = fortune_knowledge.build_agent_prompt(
                item.get("question", "未命名占测"),
                run.get("engine_id", ""),
                run.get("input", {}),
                run.get("facts", {}),
                item.get("category") or "other",
            )
            return self._ok({"reading_id": item["id"], "prompt": prompt})
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as error:
            return self._error("FORTUNE_PROMPT_FAILED", str(error))

    def create_fortune_profile(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            values = fortune_app.prepare_profile(payload)
            profile_id = fortune_storage.save_profile(self._fortune_db(), **values)
            return self._ok(
                next(
                    item
                    for item in fortune_storage.list_profiles(self._fortune_db())
                    if item["id"] == profile_id
                )
            )
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("FORTUNE_PROFILE_CREATE_FAILED", str(error))

    def update_fortune_profile(
        self, profile_id: Any, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            profile_id = self._fortune_id(profile_id, "档案编号")
            values = fortune_app.prepare_profile(payload)
            changed = fortune_storage.update_profile(self._fortune_db(), profile_id, **values)
            if not changed:
                raise ValueError("所选命主档案不存在。")
            return self._ok(
                next(
                    item
                    for item in fortune_storage.list_profiles(self._fortune_db())
                    if item["id"] == profile_id
                )
            )
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("FORTUNE_PROFILE_UPDATE_FAILED", str(error))

    def delete_fortune_profile(
        self, profile_id: Any, confirmed: Any = False
    ) -> dict[str, Any]:
        try:
            profile_id = self._fortune_id(profile_id, "档案编号")
            if confirmed is not True:
                raise ValueError("删除命主档案前请先确认。")
            deleted = fortune_storage.delete_profile(self._fortune_db(), profile_id)
            return self._ok({"deleted": deleted, "profile_id": profile_id})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_PROFILE_DELETE_FAILED", str(error))

    def create_fortune_claim(
        self, reading_id: Any, statement: Any, target_at: Any
    ) -> dict[str, Any]:
        try:
            reading_id = self._fortune_id(reading_id)
            statement = self._payload_text(
                {"statement": statement}, "statement", required=True, max_length=2_000
            )
            target_at = self._payload_text(
                {"target_at": target_at}, "target_at", required=True, max_length=32
            )
            date.fromisoformat(target_at)
            claim_id = fortune_storage.save_claim(
                self._fortune_db(),
                session_id=reading_id,
                statement=statement,
                target_at=target_at,
            )
            return self._ok({"claim_id": claim_id})
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("FORTUNE_CLAIM_CREATE_FAILED", str(error))

    def save_fortune_outcome(
        self, claim_id: Any, status: Any, note: Any = ""
    ) -> dict[str, Any]:
        try:
            claim_id = self._fortune_id(claim_id, "预测编号")
            status = self._payload_text(
                {"status": status}, "status", required=True, max_length=32
            )
            if status not in {"hit", "miss", "partial", "unknown"}:
                raise ValueError("复盘结果选项无效。")
            note = self._payload_text({"note": note}, "note", max_length=4_000)
            outcome_id = fortune_storage.save_outcome(
                self._fortune_db(), claim_id=claim_id, status=status, note=note
            )
            return self._ok({"outcome_id": outcome_id, "claim_id": claim_id})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_OUTCOME_SAVE_FAILED", str(error))

    def search_fortune_knowledge(
        self, query: Any, engine: Any = ""
    ) -> dict[str, Any]:
        try:
            query = self._payload_text({"query": query}, "query", max_length=2_000)
            engine = self._payload_text({"engine": engine}, "engine", max_length=80)
            if engine and engine not in fortune_app.ENGINE_LABELS:
                raise ValueError("术式选项无效。")
            return self._ok(fortune_knowledge.search(query, engine=engine or None))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return self._error("FORTUNE_KNOWLEDGE_SEARCH_FAILED", str(error))

    def verify_fortune_database(self) -> dict[str, Any]:
        try:
            return self._ok(fortune_storage.verify_database(self._fortune_db()))
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_DATABASE_VERIFY_FAILED", str(error))

    def backup_fortune_database(self, directory: Any = "") -> dict[str, Any]:
        try:
            if not isinstance(directory, str):
                raise ValueError("保存位置无效。")
            target = self._resolve_directory(
                directory.strip() or str(self._output_dir(self._env_values())), "保存位置"
            )
            target.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            path = target / f"fortune-backup-{stamp}.db"
            counter = 1
            while path.exists():
                path = target / f"fortune-backup-{stamp}-{counter}.db"
                counter += 1
            result = fortune_storage.backup_database(self._fortune_db(), path)
            return self._ok({"path": str(result.resolve()), "size_bytes": result.stat().st_size})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_DATABASE_BACKUP_FAILED", str(error))

    def import_fortune_database(
        self, source_path: Any, confirmed: Any = False
    ) -> dict[str, Any]:
        try:
            if confirmed is not True:
                raise ValueError("导入数据库前请先确认。")
            source = self._resolve_file(source_path, "数据库文件")
            destination = self._fortune_db().resolve()
            if source == destination:
                raise ValueError("不能把当前数据库导入自身。")
            with closing(sqlite3.connect(source)) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                required = {"reading_sessions", "engine_runs", "schema_migrations"}
                if not required <= tables or connection.execute(
                    "PRAGMA integrity_check"
                ).fetchone()[0] != "ok":
                    raise ValueError("数据库不是有效的赛博算命数据库或已经损坏。")
            replacement = destination.with_name(f".{destination.name}.importing")
            replacement.unlink(missing_ok=True)
            try:
                with closing(sqlite3.connect(source)) as current, closing(sqlite3.connect(replacement)) as target:
                    current.backup(target)
                replacement.replace(destination)
            finally:
                replacement.unlink(missing_ok=True)
            return self._ok(
                {
                    "source_path": str(source),
                    "database_path": str(destination),
                }
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("FORTUNE_DATABASE_IMPORT_FAILED", str(error))


__all__ = ["FortuneApiMixin"]
