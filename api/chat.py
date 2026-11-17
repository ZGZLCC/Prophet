"""聊天导出与聊天材料分析相关的本地 API。"""

from __future__ import annotations

from datetime import date
from pathlib import Path
import threading
from typing import Any, Mapping

import chat_analysis
import chat_export

from .base import ApiBase, MAX_SETTING_LENGTH


class ChatApiMixin:
    """聊天文件导出、检查和一键分析操作。"""

    @staticmethod
    def _optional_payload_text(
        payload: Mapping[str, Any], name: str, *, max_length: int = MAX_SETTING_LENGTH
    ) -> str:
        value = payload.get(name, "")
        if value in (None, ""):
            return ""
        return ApiBase._payload_text(payload, name, max_length=max_length)

    def _chat_output_directory(self, value: Any) -> Path:
        if value in (None, ""):
            value = str(self._output_dir(self._env_values()))
        if not isinstance(value, str):
            raise ValueError("保存位置必须是文本。")
        return self._resolve_directory(value, "保存位置")

    def _chat_export_arguments(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, Mapping):
            raise ValueError("聊天导出参数格式无效。")
        source = self._payload_text(payload, "source", required=True)
        if source not in chat_export.SOURCE_LABELS:
            raise ValueError("聊天来源无效。")
        output_format = self._payload_text(payload, "output_format", required=True).lower()
        if output_format not in chat_export.FORMATS:
            raise ValueError("导出格式无效。")
        chat_text = self._payload_text(payload, "chat_text", max_length=20_000)
        start_time = self._optional_payload_text(payload, "start_time", max_length=32)
        end_time = self._optional_payload_text(payload, "end_time", max_length=32)
        for label, value in (("开始日期", start_time), ("结束日期", end_time)):
            if value:
                try:
                    parsed_date = date.fromisoformat(value)
                except ValueError as error:
                    raise ValueError(f"{label}必须是 YYYY-MM-DD。") from error
                if parsed_date > date.today():
                    raise ValueError(f"{label}不能晚于今天。")
        if start_time and end_time and start_time > end_time:
            raise ValueError("开始日期不能晚于结束日期。")
        db_root = self._optional_payload_text(payload, "db_root", max_length=4_000)
        account = self._optional_payload_text(payload, "account", max_length=512)
        qq_key = self._optional_payload_text(payload, "qq_key", max_length=512)
        qq_pid = self._optional_payload_text(payload, "qq_pid", max_length=32)
        if qq_pid and (not qq_pid.isdigit() or int(qq_pid) < 1):
            raise ValueError("QQ.exe PID 必须是正整数。")
        recover = payload.get("recover", False)
        if not isinstance(recover, bool):
            raise ValueError("恢复模式参数无效。")
        return {
            "source": source,
            "output_dir": self._chat_output_directory(payload.get("output_dir", "")),
            "output_format": output_format,
            "chat_text": chat_text,
            "start_time": start_time or None,
            "end_time": end_time or None,
            "db_root": db_root,
            "account": account,
            "qq_key": qq_key,
            "qq_pid": qq_pid,
            "recover": recover,
        }

    @staticmethod
    def _run_chat_export(
        arguments: Mapping[str, Any], cancel_event: threading.Event
    ) -> dict[str, Any]:
        result = chat_export.run_export(cancel_event=cancel_event, **dict(arguments))
        return {
            "source": arguments["source"],
            "format": arguments["output_format"],
            "output": str(result["output"]),
            "size_bytes": result["size"],
        }

    def start_chat_export(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        try:
            arguments = self._chat_export_arguments(payload)
            cancel_event = threading.Event()
            task = self._submit_task(
                "chat-export",
                self._run_chat_export,
                arguments,
                cancel_event,
                cancel_event=cancel_event,
            )
            return self._ok(task)
        except (OSError, ValueError) as error:
            return self._error("CHAT_EXPORT_START_FAILED", str(error))

    def inspect_chat(self, path: Any) -> dict[str, Any]:
        try:
            source = self._resolve_file(path, "聊天文件")
            return self._ok(chat_analysis.inspect_chat(str(source)))
        except (OSError, ValueError) as error:
            return self._error("CHAT_INSPECT_FAILED", str(error))

    def _chat_analysis_arguments(
        self,
        input_path: Any,
        target: Any,
        output_dir: Any,
        focus: Any,
        *,
        require_input: bool = False,
        require_target: bool = False,
    ) -> dict[str, str | Path]:
        payload = {
            "input_path": input_path,
            "target": target,
            "output_dir": output_dir,
            "focus": focus,
        }
        input_value = self._optional_payload_text(payload, "input_path", max_length=4_000)
        target_value = self._optional_payload_text(payload, "target", max_length=512)
        focus_value = self._optional_payload_text(payload, "focus", max_length=2_000)
        if require_input:
            input_value = str(self._resolve_file(input_value, "聊天文件"))
        elif input_value:
            input_value = chat_analysis.clean_path(input_value)
        if require_target and not target_value:
            raise ValueError("请填写目标人物 sender。")
        destination = self._chat_output_directory(output_dir)
        return {
            "input_path": input_value,
            "target": target_value,
            "output_dir": destination,
            "focus": focus_value,
        }

    def get_chat_agent_prompt(
        self, input_path: Any, target: Any, output_dir: Any, focus: Any
    ) -> dict[str, Any]:
        try:
            arguments = self._chat_analysis_arguments(input_path, target, output_dir, focus)
            return self._ok(
                {
                    "prompt": chat_analysis.build_agent_prompt(
                        str(arguments["input_path"]),
                        str(arguments["target"]),
                        str(arguments["output_dir"]),
                        str(arguments["focus"]),
                    ),
                    "output_dir": str(arguments["output_dir"]),
                }
            )
        except (OSError, ValueError) as error:
            return self._error("CHAT_PROMPT_FAILED", str(error))

    def get_chat_manual_commands(
        self, input_path: Any, target: Any, output_dir: Any, focus: Any
    ) -> dict[str, Any]:
        try:
            arguments = self._chat_analysis_arguments(input_path, target, output_dir, focus)
            work_root = self.app_home / ".chat-material-work"
            output_path, work_dir = chat_analysis.generated_paths(
                str(arguments["output_dir"]),
                str(arguments["target"]),
                work_root=work_root,
            )
            return self._ok(
                {
                    "commands": chat_analysis.build_manual_commands(
                        str(arguments["input_path"]),
                        str(arguments["target"]),
                        str(arguments["output_dir"]),
                        str(arguments["focus"]),
                        work_root=work_root,
                        output_path=output_path,
                        work_dir=work_dir,
                    ),
                    "output": str(output_path),
                    "work_dir": str(work_dir),
                }
            )
        except (OSError, ValueError) as error:
            return self._error("CHAT_COMMANDS_FAILED", str(error))

    @staticmethod
    def _run_chat_analysis(
        arguments: Mapping[str, Any], cancel_event: threading.Event
    ) -> dict[str, Any]:
        result = chat_analysis.run_one_click(
            str(arguments["input_path"]),
            str(arguments["target"]),
            str(arguments["output_dir"]),
            str(arguments["focus"]),
            cancel_event=cancel_event,
            work_root=arguments["work_root"],
            env_file=arguments["env_file"],
        )
        return {
            "full_report": result["full_report"],
            "core_report": result["core_report"],
        }

    def start_chat_analysis(
        self, input_path: Any, target: Any, output_dir: Any = "", focus: Any = ""
    ) -> dict[str, Any]:
        try:
            arguments = self._chat_analysis_arguments(
                input_path,
                target,
                output_dir,
                focus,
                require_input=True,
                require_target=True,
            )
            arguments["work_root"] = self.app_home / ".chat-material-work"
            arguments["env_file"] = self.env_path
            cancel_event = threading.Event()
            task = self._submit_task(
                "chat-analysis",
                self._run_chat_analysis,
                arguments,
                cancel_event,
                cancel_event=cancel_event,
            )
            return self._ok(task)
        except (OSError, ValueError) as error:
            return self._error("CHAT_ANALYSIS_START_FAILED", str(error))


__all__ = ["ChatApiMixin"]
