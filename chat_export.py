"""Small Windows-only bridge to the existing QQ and WeChat exporters."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from process_runner import ProcessCancelled, run_process


ROOT = Path(__file__).resolve().parent
APP_HOME = Path(os.getenv("PROPHET_HOME", ROOT))
_configured_output = Path(os.getenv("PROPHET_OUTPUT_DIR", "output")).expanduser()
DEFAULT_OUTPUT_DIR = (
    _configured_output if _configured_output.is_absolute() else APP_HOME / _configured_output
)
FORMATS = ("json", "txt", "csv")
SOURCE_LABELS = {"qq": "QQ", "wechat": "微信"}
SCRIPT_PATHS = {
    "qq": ROOT / "exporters" / "qq" / "export_qq_text.py",
    "wechat": ROOT / "exporters" / "wechat" / "export_wechat_text.py",
}


class ExportToolError(RuntimeError):
    """An exporter could not be found or did not finish successfully."""


def split_chats(value: str) -> list[str]:
    """Turn comma/newline-separated chat selectors into CLI arguments."""
    return [item.strip() for item in value.replace("\n", ",").split(",") if item.strip()]


def find_script(source: str) -> Path | None:
    if source not in SOURCE_LABELS:
        raise ValueError(f"不支持的导出来源：{source}")
    path = SCRIPT_PATHS[source]
    return path if path.is_file() else None


def _new_output_path(output_dir: Path, source: str, output_format: str) -> Path:
    prefix = "qq-text" if source == "qq" else "wechat-text"
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"{prefix}-{stamp}.{output_format}"
    suffix = 1
    while path.exists():
        path = output_dir / f"{prefix}-{stamp}-{suffix}.{output_format}"
        suffix += 1
    return path


def build_command(
    source: str,
    output_dir: Path,
    output_format: str,
    chat_text: str = "",
    start_time: str | None = None,
    end_time: str | None = None,
    db_root: str = "",
    account: str = "",
    qq_key: str = "",
    qq_pid: str = "",
    recover: bool = False,
) -> tuple[list[str], Path | None]:
    if source not in SOURCE_LABELS:
        raise ValueError(f"不支持的导出来源：{source}")
    if output_format not in FORMATS:
        raise ValueError(f"不支持的导出格式：{output_format}")
    script = find_script(source)
    if script is None:
        raise ExportToolError(f"未找到 {SOURCE_LABELS[source]} Windows 导出脚本。")

    command = [sys.executable, str(script), "--format", output_format]
    expected_output = None
    if source == "qq":
        command.extend(("--output-dir", str(output_dir)))
        if qq_key.strip():
            command.extend(("--key", qq_key.strip()))
        if qq_pid.strip():
            command.extend(("--pid", qq_pid.strip()))
        if recover:
            command.append("--recover")
    else:
        expected_output = _new_output_path(output_dir, source, output_format)
        command.extend(("--output", str(expected_output)))
        if account.strip():
            command.extend(("--account", account.strip()))

    if db_root.strip():
        command.extend(("--db-root", db_root.strip()))
    for chat in split_chats(chat_text):
        command.extend(("--chat", chat))
    if start_time:
        command.extend(("--start-time", start_time))
    if end_time:
        command.extend(("--end-time", end_time))
    return command, expected_output


def _output_from_logs(source: str, stdout: str, output_dir: Path, output_format: str) -> Path | None:
    for line in stdout.splitlines():
        if source == "qq" and "->" in line:
            candidate = Path(line.rsplit("->", 1)[1].strip().strip('"'))
            if candidate.is_file():
                return candidate
        if source == "wechat" and line.startswith("OUTPUT="):
            candidate = Path(line.removeprefix("OUTPUT=").strip())
            if candidate.is_file():
                return candidate
    prefix = "qq-text" if source == "qq" else "wechat-text"
    candidates = sorted(
        output_dir.glob(f"{prefix}-*.{output_format}"),
        key=lambda path: path.stat().st_mtime,
    )
    return candidates[-1] if candidates else None


def _export_files(output_dir: Path, source: str, output_format: str) -> set[Path]:
    prefix = "qq-text" if source == "qq" else "wechat-text"
    return {
        path
        for path in output_dir.glob(f"{prefix}-*.{output_format}*")
        if path.is_file()
        and path.name.endswith((f".{output_format}", f".{output_format}.tmp"))
    }


def _remove_created_outputs(
    output_dir: Path, source: str, output_format: str, before: set[Path]
) -> None:
    for path in _export_files(output_dir, source, output_format) - before:
        try:
            path.unlink()
        except OSError:
            pass


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "[已隐藏]") if len(secret) >= 4 else text


def run_export(
    source: str,
    output_dir: str | Path,
    output_format: str,
    chat_text: str = "",
    start_time: str | None = None,
    end_time: str | None = None,
    db_root: str = "",
    account: str = "",
    qq_key: str = "",
    qq_pid: str = "",
    recover: bool = False,
    cancel_event: Event | None = None,
) -> dict[str, str | int | Path]:
    if os.name != "nt":
        raise ExportToolError("聊天导出页面仅支持 Windows。")
    if not str(output_dir).strip():
        raise ValueError("导出位置不能为空")
    output_path = Path(output_dir).expanduser()
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ExportToolError(f"无法创建导出位置：{output_path}\n{exc}") from exc

    command, expected_output = build_command(
        source,
        output_path.resolve(),
        output_format,
        chat_text,
        start_time,
        end_time,
        db_root,
        account,
        qq_key,
        qq_pid,
        recover,
    )
    script = find_script(source)
    if script is None:
        raise ExportToolError(f"未找到 {SOURCE_LABELS[source]} Windows 导出脚本。")
    before = _export_files(output_path.resolve(), source, output_format)
    try:
        if cancel_event is None:
            completed = subprocess.run(
                command,
                cwd=script.parent,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                timeout=7_200,
            )
        else:
            completed = run_process(
                command,
                cwd=str(script.parent),
                stdin=subprocess.DEVNULL,
                timeout=7_200,
                cancel_event=cancel_event,
            )
    except ProcessCancelled:
        _remove_created_outputs(output_path.resolve(), source, output_format, before)
        raise
    except subprocess.TimeoutExpired as exc:
        _remove_created_outputs(output_path.resolve(), source, output_format, before)
        raise ExportToolError("导出超过 2 小时，已停止；请缩小聊天或时间范围后重试。") from exc
    except OSError as exc:
        _remove_created_outputs(output_path.resolve(), source, output_format, before)
        raise ExportToolError(f"无法启动导出脚本：{exc}") from exc

    stdout = _redact(completed.stdout or "", qq_key.strip())
    stderr = _redact(completed.stderr or "", qq_key.strip())
    if completed.returncode != 0:
        _remove_created_outputs(output_path.resolve(), source, output_format, before)
        details = (stderr.strip() or stdout.strip())[-8_000:]
        raise ExportToolError(f"{SOURCE_LABELS[source]} 导出失败。\n{details}")

    output_file = expected_output if expected_output and expected_output.is_file() else _output_from_logs(
        source, stdout, output_path.resolve(), output_format
    )
    if output_file is None or not output_file.is_file():
        _remove_created_outputs(output_path.resolve(), source, output_format, before)
        raise ExportToolError("脚本执行成功，但没有找到导出文件。\n" + stdout[-2_000:])
    return {
        "output": output_file.resolve(),
        "stdout": stdout,
        "stderr": stderr,
        "size": output_file.stat().st_size,
    }


if __name__ == "__main__":
    assert split_chats("张三, 群聊\nwxid_test") == ["张三", "群聊", "wxid_test"]
    assert split_chats("  ") == []
    print("chat_export self-check passed")
