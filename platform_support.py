"""Per-platform app paths, theme detection, and capability flags."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


APP_NAME = "Prophet"

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

# 聊天导出依赖 Windows 客户端实现：进程内存取密钥、tasklist 查进程、winreg 定位数据目录。
CHAT_EXPORT_SUPPORTED = IS_WINDOWS

# macOS 的窗口图标由 .app 的 .icns 决定，pywebview 不需要单独传。
WINDOW_ICON_NAME = "prophet_icon_light.ico" if IS_WINDOWS else None


def platform_tag() -> str:
    """给前端和日志用的稳定平台标识。"""
    if IS_WINDOWS:
        return "windows"
    if IS_MACOS:
        return "macos"
    return sys.platform or "unknown"


def app_home() -> Path:
    """免安装版的默认用户数据目录。"""
    if IS_WINDOWS:
        return Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
    if IS_MACOS:
        return Path.home() / "Library" / "Application Support" / APP_NAME
    return Path.home() / ".local" / "share" / APP_NAME


def window_icon(resource_root: Path) -> str | None:
    """返回 pywebview 需要的窗口图标路径；不需要或缺失时返回 None。"""
    if not WINDOW_ICON_NAME:
        return None
    path = resource_root / "assets" / WINDOW_ICON_NAME
    return str(path) if path.is_file() else None


def dark_mode() -> bool:
    """读取系统是否处于深色模式，读不到时按浅色处理。"""
    if IS_WINDOWS:
        return _windows_dark_mode()
    if IS_MACOS:
        return _macos_dark_mode()
    return False


def _windows_dark_mode() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except (ImportError, OSError):
        return False


def _macos_dark_mode() -> bool:
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip().lower() == "dark"
