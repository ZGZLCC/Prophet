"""Pure chat-analysis helpers used by the native shell."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from threading import Event

from process_runner import ProcessCancelled, run_process


ROOT = Path(__file__).resolve().parent
APP_HOME = Path(os.getenv("PROPHET_HOME", ROOT))
EXTRACTOR_DIR = ROOT / "chat-material-extractor"
EXTRACTOR_SCRIPT = EXTRACTOR_DIR / "scripts" / "extract.py"
PROJECT_ENV = APP_HOME / ".env"
_configured_output = Path(os.getenv("PROPHET_OUTPUT_DIR", "output")).expanduser()
DEFAULT_OUTPUT_DIR = (
    _configured_output if _configured_output.is_absolute() else APP_HOME / _configured_output
)
DEFAULT_WORK_ROOT = APP_HOME / ".chat-material-work"
PYTHON_COMMAND = "'" + sys.executable.replace("'", "''") + "'" if getattr(sys, "frozen", False) else "python"


class ChatAnalysisError(ValueError):
    """The extractor could not inspect or generate the requested report."""


def clean_path(value: str) -> str:
    return value.strip().strip('"')


def powershell_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def generated_paths(
    output_dir: str, target: str, *, work_root: Path | None = None
) -> tuple[Path, Path]:
    safe_sender = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", target.strip()).strip(" .") or "待选择sender"
    stem = f"{safe_sender}-{datetime.now():%Y%m%d-%H%M%S}"
    return (
        Path(output_dir or str(DEFAULT_OUTPUT_DIR)) / f"{stem}.md",
        (work_root or DEFAULT_WORK_ROOT) / stem,
    )


def inspect_chat(path_text: str, *, cancel_event: Event | None = None) -> dict:
    path = Path(clean_path(path_text))
    if not path.is_file():
        raise ValueError(f"找不到聊天文件：{path}")
    if not EXTRACTOR_SCRIPT.is_file():
        raise ValueError(f"找不到项目内分析脚本：{EXTRACTOR_SCRIPT}")
    try:
        if cancel_event is None:
            completed = subprocess.run(
                [sys.executable, str(EXTRACTOR_SCRIPT), "inspect", str(path.resolve())],
                cwd=str(EXTRACTOR_DIR),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=600,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        else:
            completed = run_process(
                [sys.executable, str(EXTRACTOR_SCRIPT), "inspect", str(path.resolve())],
                cwd=str(EXTRACTOR_DIR),
                timeout=600,
                cancel_event=cancel_event,
            )
    except subprocess.TimeoutExpired as error:
        raise ValueError("检查聊天文件超过 10 分钟，可能是文件过大或格式异常。") from error
    except ProcessCancelled:
        raise
    except OSError as error:
        raise ValueError(f"无法启动聊天文件检查：{error}") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "未知错误"
        raise ValueError(detail[-4_000:])
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"分析脚本返回了无法读取的结果：{error}") from error


def build_agent_prompt(
    input_path: str,
    target: str,
    output_dir: str,
    focus: str,
) -> str:
    input_path = input_path or "<聊天 JSON/JSONL 文件路径>"
    target_line = (
        f"目标人物 sender：{target}"
        if target
        else "目标人物 sender：尚未确定。请先运行 inspect，列出 sender 后让我选择，禁止猜测。"
    )
    focus_line = focus or "未指定；按默认流程覆盖可观察的语言、情绪、互动、冲突、支持和事件。"
    return f"""请使用项目内的 chat-material-extractor 处理聊天记录。

项目目录：{ROOT}
聊天文件：{input_path}
{target_line}
输出位置：{output_dir or DEFAULT_OUTPUT_DIR}
关注主题：{focus_line}

报告文件名使用准确的 sender 加当前时间，格式为 sender-YYYYMMDD-HHMMSS.md。
请保留自动生成的隐藏工作目录，方便以后继续补查。
如果目标人物 sender 不明确，请先运行 inspect，列出 sender 后让我选择，禁止猜测。
请按项目的分步流程完成处理，不要把完整聊天文件一次性发送给模型；完成后告诉我实际生成的 Markdown 报告路径。"""


def build_manual_commands(
    input_path: str,
    target: str,
    output_dir: str,
    focus: str,
    *,
    work_root: Path | None = None,
    output_path: Path | None = None,
    work_dir: Path | None = None,
) -> str:
    if output_path is None or work_dir is None:
        output_path, work_dir = generated_paths(output_dir, target, work_root=work_root)
    extractor = powershell_quote(str(EXTRACTOR_DIR))
    script = "scripts/extract.py"
    chat = powershell_quote(input_path or "<聊天文件路径>")
    chosen_target = powershell_quote(target or "<复制 inspect 输出中的准确 sender>")
    output = powershell_quote(str(output_path))
    work = powershell_quote(str(work_dir))
    overall_input = powershell_quote(str(work_dir / "overall-input.json"))
    focus_line = f"# 可选定向补查：{focus}" if focus else "# 如需定向补查，再填写 search 的 query。"
    return f"""# 手动处理方式：在 chat-material-extractor 目录中执行
Set-Location {extractor}
$chat = {chat}
$target = {chosen_target}
$work = {work}
$output = {output}

# 1. 不确定目标人物时先执行，复制准确 sender
{PYTHON_COMMAND} {script} inspect $chat

# 2. 本地整理、统计、分期和选取 Chunk
{PYTHON_COMMAND} {script} prepare $chat --target $target --work-dir $work

# 3. 重复执行：next 输出交给 Agent，按 prompts/extract_material.md 的 A 部分生成 JSON，保存后 record
{PYTHON_COMMAND} {script} next --work-dir $work
{PYTHON_COMMAND} {script} record --work-dir $work .\\batch-result.json

{focus_line}
# {PYTHON_COMMAND} {script} search --work-dir $work --query '冲突 压力'

# 4. 重复执行：取一期 Material → 按提示词 B 部分交给 Agent → 保存并记录
{PYTHON_COMMAND} {script} summary-next --work-dir $work
{PYTHON_COMMAND} {script} record-summary --work-dir $work .\\period-summary.json

# 5. 生成跨期输入，按提示词 C 部分交给 Agent，保存为 overall.json 后记录
{PYTHON_COMMAND} {script} overall-input --work-dir $work --output {overall_input}
{PYTHON_COMMAND} {script} record-overall --work-dir $work .\\overall.json

# 6. 构建完整报告和核心报告
{PYTHON_COMMAND} {script} build --work-dir $work --output $output --keep-work
    """


def run_one_click(
    input_path: str,
    target: str,
    output_dir: str,
    focus: str,
    *,
    cancel_event: Event | None = None,
    work_root: Path | None = None,
    env_file: Path | None = None,
) -> dict[str, str]:
    chat_path = Path(clean_path(input_path))
    if not chat_path.is_file():
        raise ValueError(f"找不到聊天文件：{chat_path}")
    if not EXTRACTOR_SCRIPT.is_file():
        raise ValueError(f"找不到项目内分析脚本：{EXTRACTOR_SCRIPT}")
    if not target.strip():
        raise ValueError("请填写目标人物 sender。")
    destination = clean_path(output_dir) or str(DEFAULT_OUTPUT_DIR)
    output_path, work_dir = generated_paths(destination, target, work_root=work_root)
    command = [
        sys.executable,
        str(EXTRACTOR_SCRIPT),
        "run",
        str(chat_path.resolve()),
        "--target",
        target.strip(),
        "--output",
        str(output_path),
        "--work-dir",
        str(work_dir),
        "--env-file",
        str(env_file or PROJECT_ENV),
        "--keep-work",
    ]
    if focus:
        command.extend(("--focus", focus.strip()))
    try:
        if cancel_event is None:
            completed = subprocess.run(
                command,
                cwd=str(EXTRACTOR_DIR),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=86_400,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False,
            )
        else:
            completed = run_process(
                command,
                cwd=str(EXTRACTOR_DIR),
                stdin=subprocess.DEVNULL,
                timeout=86_400,
                cancel_event=cancel_event,
            )
    except subprocess.TimeoutExpired as error:
        raise ChatAnalysisError("分析超过 24 小时，已停止。") from error
    except ProcessCancelled:
        raise
    except OSError as error:
        raise ChatAnalysisError(f"无法启动分析：{error}") from error
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip() or "未知错误"
        raise ChatAnalysisError(detail[-8_000:])
    core_path = output_path.with_name(f"{output_path.stem}_core{output_path.suffix}")
    if not output_path.is_file() or not core_path.is_file():
        raise ChatAnalysisError("分析已经结束，但没有找到生成的报告。")
    return {
        "full_report": str(output_path.resolve()),
        "core_report": str(core_path.resolve()),
        "stderr": completed.stderr or "",
    }


__all__ = [
    "APP_HOME",
    "ChatAnalysisError",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_WORK_ROOT",
    "EXTRACTOR_DIR",
    "EXTRACTOR_SCRIPT",
    "build_agent_prompt",
    "build_manual_commands",
    "clean_path",
    "generated_paths",
    "inspect_chat",
    "run_one_click",
]
