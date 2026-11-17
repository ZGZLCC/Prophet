"""人物画像与材料分析相关的本地 API。"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from person_profile import analysis, parsers, storage
from person_profile.export import build_markdown_export

from .base import MAX_SETTING_LENGTH


class ProfileApiMixin:
    """人物、材料、画像版本和预测操作。"""

    def list_people(self) -> dict[str, Any]:
        try:
            return self._ok(storage.list_people(self._sentiment_db()))
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("PEOPLE_READ_FAILED", str(error))

    def get_person_workspace(self, person_id: Any) -> dict[str, Any]:
        try:
            return self._ok(self._workspace(person_id))
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("PERSON_READ_FAILED", str(error))

    def create_person(self, name: Any, notes: Any = "") -> dict[str, Any]:
        try:
            clean_name = self._payload_text({"name": name}, "name", required=True)
            clean_notes = self._payload_text({"notes": notes}, "notes", max_length=100)
            db_path = self._sentiment_db()
            person_id = storage.create_person(db_path, clean_name, clean_notes)
            return self._ok(self._workspace(person_id))
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("PERSON_CREATE_FAILED", str(error))

    def update_person(self, person_id: Any, name: Any, notes: Any = "") -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            clean_name = self._payload_text({"name": name}, "name", required=True)
            clean_notes = self._payload_text({"notes": notes}, "notes", max_length=100)
            db_path = self._sentiment_db()
            storage.update_person(db_path, person_id, clean_name, clean_notes)
            return self._ok(self._workspace(person_id))
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("PERSON_UPDATE_FAILED", str(error))

    def delete_person(self, person_id: Any) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            deleted = storage.delete_person(self._sentiment_db(), person_id)
            return self._ok({"deleted": deleted, "person_id": person_id})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("PERSON_DELETE_FAILED", str(error))

    def set_entry_active(
        self, person_id: Any, entry_id: Any, is_active: Any
    ) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            entry_id = self._person_id(entry_id)
            if not isinstance(is_active, bool):
                raise ValueError("材料状态无效。")
            changed = storage.set_entry_active(
                self._sentiment_db(), person_id, entry_id, is_active
            )
            if not changed:
                raise ValueError("材料不存在或不属于当前人物。")
            return self._ok(self._workspace(person_id))
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("ENTRY_UPDATE_FAILED", str(error))

    def preview_material(self, path: Any, encoding: Any = "") -> dict[str, Any]:
        try:
            if not isinstance(path, str) or not path.strip():
                raise ValueError("材料文件路径不能为空。")
            if not isinstance(encoding, str):
                raise ValueError("文件编码无效。")
            encoding = encoding.strip() or None
            if encoding is not None and encoding not in parsers.TEXT_ENCODINGS:
                raise ValueError("文件编码不受支持。")
            source = Path(path.strip().strip('"')).expanduser().resolve()
            if not source.is_file():
                raise ValueError("所选材料文件不存在。")
            parsed = parsers.parse_file(
                source.name,
                source.read_bytes(),
                encoding=encoding,
            )
            return self._ok(
                {
                    "path": str(source),
                    "name": parsed.name,
                    "extension": parsed.extension,
                    "mime_type": parsed.mime_type,
                    "entry_type": "document",
                    "content": parsed.text,
                    "preview": parsed.text[:5_000],
                    "characters": len(parsed.text),
                    "size_bytes": source.stat().st_size,
                }
            )
        except parsers.EncodingRequiredError as error:
            return self._error("ENCODING_REQUIRED", str(error))
        except (OSError, ValueError, parsers.ParserError) as error:
            return self._error("MATERIAL_PREVIEW_FAILED", str(error))

    def check_material(self, person_id: Any, content: Any) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            if not isinstance(content, str):
                raise ValueError("材料内容必须是文本。")
            db_path = self._sentiment_db()
            if storage.get_person(db_path, person_id) is None:
                raise ValueError(f"人物不存在：{person_id}")
            normalized = storage.normalize_text(content)
            if not normalized:
                return self._ok({"characters": 0, "duplicate": None})
            if len(normalized) > parsers.max_text_chars():
                raise ValueError("材料内容超过 MAX_TEXT_CHARS 上限。")
            duplicate = storage.find_duplicate(
                db_path, person_id, storage.content_hash(normalized)
            )
            return self._ok({"characters": len(normalized), "duplicate": duplicate})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("MATERIAL_CHECK_FAILED", str(error))

    @staticmethod
    def _material_arguments(payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("材料参数格式无效。")
        content = payload.get("content", "")
        if not isinstance(content, str):
            raise ValueError("材料内容必须是文本。")
        content = storage.normalize_text(content)
        if not content:
            raise ValueError("材料内容不能为空。")
        if len(content) > parsers.max_text_chars():
            raise ValueError("材料内容超过 MAX_TEXT_CHARS 上限。")
        entry_type = payload.get("entry_type", "text")
        if entry_type not in {"text", "document"}:
            raise ValueError("材料类型无效。")
        source_name = payload.get("source_name", "直接输入")
        if not isinstance(source_name, str):
            raise ValueError("材料标题必须是文本。")
        source_name = source_name.strip() or "直接输入"
        if len(source_name) > MAX_SETTING_LENGTH:
            raise ValueError("材料标题过长。")
        file_type = payload.get("file_type")
        if file_type is not None and not isinstance(file_type, str):
            raise ValueError("文件类型无效。")
        occurred_at = payload.get("occurred_at")
        if occurred_at is not None and not isinstance(occurred_at, str):
            raise ValueError("材料发生日期无效。")
        occurred_at = occurred_at.strip() if occurred_at else None
        if occurred_at:
            try:
                occurred_date = date.fromisoformat(occurred_at)
            except ValueError as error:
                raise ValueError("材料发生日期必须是 YYYY-MM-DD。") from error
            today = date.today()
            earliest = date(
                today.year - 50,
                today.month,
                min(today.day, monthrange(today.year - 50, today.month)[1]),
            )
            if not earliest <= occurred_date <= today:
                raise ValueError("材料发生日期需在最近 50 年内且不能晚于今天。")
        context = payload.get("context", "")
        if not isinstance(context, str):
            raise ValueError("场景备注必须是文本。")
        if len(context) > MAX_SETTING_LENGTH:
            raise ValueError("场景备注过长。")
        allow_duplicate = payload.get("allow_duplicate", False)
        if not isinstance(allow_duplicate, bool):
            raise ValueError("重复材料选项无效。")
        return {
            "entry_type": entry_type,
            "source_name": source_name,
            "file_type": file_type.strip() if isinstance(file_type, str) else None,
            "occurred_at": occurred_at,
            "context": context.strip(),
            "content": content,
            "allow_duplicate": allow_duplicate,
        }

    def start_material_analysis(
        self, person_id: Any, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            arguments = self._material_arguments(payload)
            db_path = self._sentiment_db()
            duplicate = storage.find_duplicate(
                db_path, person_id, storage.content_hash(arguments["content"])
            )
            if duplicate is not None and not arguments["allow_duplicate"]:
                return self._error(
                    "DUPLICATE_MATERIAL",
                    f"该人物已有相同材料（材料 #{duplicate['id']}）。",
                )
            arguments.pop("allow_duplicate")
            task = self._submit_task(
                "material-analysis",
                analysis.analyze_and_save,
                str(db_path),
                person_id,
                **arguments,
            )
            return self._ok(task)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("MATERIAL_ANALYSIS_START_FAILED", str(error))

    def start_prediction(
        self, person_id: Any, event_text: Any, profile_version: Any = None
    ) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            if not isinstance(event_text, str):
                raise ValueError("预测事件必须是文本。")
            event_text = storage.normalize_text(event_text)
            if not event_text:
                raise ValueError("预测事件不能为空。")
            if len(event_text) > parsers.max_text_chars():
                raise ValueError("预测事件过长。")
            if profile_version in (None, ""):
                selected_version = None
            else:
                selected_version = self._person_id(profile_version)
            task = self._submit_task(
                "prediction",
                analysis.predict_and_save,
                str(self._sentiment_db()),
                person_id,
                event_text,
                profile_version=selected_version,
            )
            return self._ok(task)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("PREDICTION_START_FAILED", str(error))

    def start_prediction_review(
        self, person_id: Any, prediction_id: Any, actual_outcome: Any
    ) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            prediction_id = self._person_id(prediction_id)
            if not isinstance(actual_outcome, str):
                raise ValueError("实际结果必须是文本。")
            actual_outcome = storage.normalize_text(actual_outcome)
            if not actual_outcome:
                raise ValueError("实际结果不能为空。")
            if len(actual_outcome) > parsers.max_text_chars():
                raise ValueError("实际结果过长。")
            task = self._submit_task(
                "prediction-review",
                analysis.review_and_save,
                str(self._sentiment_db()),
                person_id,
                prediction_id,
                actual_outcome,
            )
            return self._ok(task)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("REVIEW_START_FAILED", str(error))

    def delete_prediction(self, person_id: Any, prediction_id: Any) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            prediction_id = self._person_id(prediction_id)
            deleted = storage.delete_prediction(
                self._sentiment_db(), person_id, prediction_id
            )
            return self._ok({"deleted": deleted, "prediction_id": prediction_id})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("PREDICTION_DELETE_FAILED", str(error))

    def start_rebuild_profile(self, person_id: Any) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            task = self._submit_task(
                "profile-rebuild",
                analysis.rebuild_profile,
                str(self._sentiment_db()),
                person_id,
            )
            return self._ok(task)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("PROFILE_REBUILD_START_FAILED", str(error))

    def restore_profile_version(
        self, person_id: Any, version: Any
    ) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            version = self._person_id(version)
            result = analysis.restore_profile(
                str(self._sentiment_db()), person_id, version
            )
            return self._ok(result)
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("PROFILE_RESTORE_FAILED", str(error))

    def export_person(
        self, person_id: Any, export_format: Any = "json", directory: Any = ""
    ) -> dict[str, Any]:
        try:
            person_id = self._person_id(person_id)
            if not isinstance(export_format, str):
                raise ValueError("导出格式无效。")
            export_format = export_format.strip().lower()
            if export_format not in {"json", "markdown", "database"}:
                raise ValueError("仅支持 JSON、Markdown 或数据库备份。")
            if not isinstance(directory, str):
                raise ValueError("保存位置无效。")
            values = self._env_values()
            target = self._resolve_directory(
                directory.strip() or str(self._output_dir(values)), "保存位置"
            )
            target.mkdir(parents=True, exist_ok=True)
            db_path = self._sentiment_db()
            bundle = storage.export_person(db_path, person_id)
            if bundle is None:
                raise ValueError(f"人物不存在：{person_id}")
            stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
            suffix = {"json": "json", "markdown": "md", "database": "db"}[export_format]
            stem = (
                f"person-{person_id}-{stamp}"
                if export_format != "database"
                else f"sentiment-backup-{stamp}"
            )
            output = target / f"{stem}.{suffix}"
            counter = 1
            while output.exists():
                output = target / f"{stem}-{counter}.{suffix}"
                counter += 1
            if export_format == "json":
                output.write_text(
                    json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            elif export_format == "markdown":
                output.write_text(build_markdown_export(bundle), encoding="utf-8")
            else:
                output.write_bytes(storage.backup_database(db_path))
            return self._ok(
                {
                    "format": export_format,
                    "path": str(output.resolve()),
                    "size_bytes": output.stat().st_size,
                }
            )
        except (OSError, ValueError, KeyError, sqlite3.Error) as error:
            return self._error("PERSON_EXPORT_FAILED", str(error))

    def import_database(self, source_path: Any, confirmed: Any = False) -> dict[str, Any]:
        try:
            if not isinstance(source_path, str) or not source_path.strip():
                raise ValueError("数据库文件路径不能为空。")
            if confirmed is not True:
                raise ValueError("导入数据库前请先确认会替换当前人物数据。")
            source = Path(source_path.strip().strip('"')).expanduser().resolve()
            if not source.is_file():
                raise ValueError("所选数据库文件不存在。")
            destination = self._sentiment_db()
            storage.restore_database(destination, source.read_bytes())
            return self._ok({"restored": True, "path": str(source)})
        except (OSError, ValueError, sqlite3.Error) as error:
            return self._error("DATABASE_IMPORT_FAILED", str(error))


__all__ = ["ProfileApiMixin"]
