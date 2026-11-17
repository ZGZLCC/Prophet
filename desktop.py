"""Native pywebview launcher for Prophet."""

from __future__ import annotations

import os
from pathlib import Path
import runpy
import shutil
import sys


FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)).resolve()
DEFAULT_HOME = (
    Path(os.getenv("LOCALAPPDATA", Path.home())) / "Prophet"
    if FROZEN
    else RESOURCE_ROOT
)
APP_HOME = Path(os.getenv("PROPHET_HOME", DEFAULT_HOME)).expanduser().resolve()
TRUSTED_SCRIPTS = {
    (RESOURCE_ROOT / "exporters" / "qq" / "export_qq_text.py").resolve(),
    (RESOURCE_ROOT / "exporters" / "wechat" / "export_wechat_text.py").resolve(),
    (RESOURCE_ROOT / "chat-material-extractor" / "scripts" / "extract.py").resolve(),
}
WINDOW_TITLE = "Prophet"
WINDOW_SIZE = (1100, 760)
MIN_WINDOW_SIZE = (820, 600)


def prepare_app_home() -> None:
    APP_HOME.mkdir(parents=True, exist_ok=True)
    env_path = APP_HOME / ".env"
    template = RESOURCE_ROOT / ".env.example"
    if FROZEN and not env_path.exists() and template.is_file():
        shutil.copyfile(template, env_path)
    os.environ["PROPHET_HOME"] = str(APP_HOME)


def dispatch_bundled_script() -> bool:
    """Reuse the frozen executable as the Python host for bundled tools."""

    if not FROZEN or len(sys.argv) < 2:
        return False
    script = Path(sys.argv[1]).resolve()
    if script not in TRUSTED_SCRIPTS:
        return False
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.argv.pop(1)
    runpy.run_path(str(script), run_name="__main__")
    return True


def system_uses_dark_mode() -> bool:
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def check_gui_backend() -> None:
    """确认 pywebview 的窗口后端能加载。

    缺 pythonnet、.NET Framework 不可用或位数不匹配时，``webview.start()`` 会直接抛异常；
    在自检里提前加载一次，让构建失败在打包阶段就暴露，而不是等到用户双击才发现。
    """
    import importlib
    import platform

    if platform.system() != "Windows":
        return
    try:
        importlib.import_module("webview.platforms.winforms")
    except Exception as exc:  # noqa: BLE001 - ImportError、RuntimeError 都会出现
        raise RuntimeError(
            "pywebview 的 WinForms 后端加载失败，窗口无法启动；"
            "请检查 pythonnet 与 .NET Framework 4.8 是否可用。"
            f"原始错误：{type(exc).__name__}: {exc}"
        ) from exc


def run_self_test() -> None:
    prepare_app_home()
    import io

    import cryptography
    import docx
    import izthon
    import lunar_python
    import openpyxl
    import pypdf
    import webview

    from app_api import AppApi
    from fortune.engines import cast_ziwei
    import parsers

    for path in (
        RESOURCE_ROOT / "web" / "index.html",
        RESOURCE_ROOT / "web" / "styles.css",
        RESOURCE_ROOT / "web" / "app.js",
        *(RESOURCE_ROOT / "web" / "modules").glob("*.js"),
        *(RESOURCE_ROOT / "web" / "styles").glob("*.css"),
        RESOURCE_ROOT / "assets" / "prophet_icon_light.ico",
        *TRUSTED_SCRIPTS,
    ):
        assert path.is_file(), path
    document = docx.Document()
    document.add_paragraph("DOCX self-test")
    document_bytes = io.BytesIO()
    document.save(document_bytes)
    assert "DOCX self-test" in parsers.parse_file("test.docx", document_bytes.getvalue()).text
    workbook = openpyxl.Workbook()
    workbook.active.append(["XLSX self-test"])
    workbook_bytes = io.BytesIO()
    workbook.save(workbook_bytes)
    workbook.close()
    assert "XLSX self-test" in parsers.parse_file("test.xlsx", workbook_bytes.getvalue()).text
    assert cast_ziwei(
        birth_at="1900-01-01T23:00:00+08:00",
        gender="male",
        time_policy_id="civil-standard-time-v1",
        flow_year_start=2000,
        flow_year_count=1,
    )["engineId"] == "ziwei"
    assert AppApi(resource_root=RESOURCE_ROOT, app_home=APP_HOME).get_app_info()["ok"]
    assert all((cryptography, docx, izthon, lunar_python, openpyxl, pypdf, webview))
    check_gui_backend()
    print("native desktop self-check passed")


def main() -> None:
    prepare_app_home()
    if dispatch_bundled_script():
        return

    import webview
    from app_api import AppApi

    api = AppApi(resource_root=RESOURCE_ROOT, app_home=APP_HOME)
    window = webview.create_window(
        WINDOW_TITLE,
        url=(RESOURCE_ROOT / "web" / "index.html").as_uri(),
        js_api=api,
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=MIN_WINDOW_SIZE,
        hidden=True,
        background_color="#080808" if system_uses_dark_mode() else "#ffffff",
    )
    def show_window() -> None:
        window.show()
        window.evaluate_js('window.dispatchEvent(new Event("prophetwindowshown"))')

    window.events.loaded += show_window
    api.set_window(window)
    webview.start(icon=str(RESOURCE_ROOT / "assets" / "prophet_icon_light.ico"))


def report_self_test_failure(exc: BaseException) -> None:
    """把自检失败的完整 traceback 写到可用流。

    打包版是窗口程序，没有控制台时 ``sys.stderr`` 和 ``sys.stdout`` 都是 None，
    异常会完全丢失；构建脚本用重定向抓取的正是这条流。
    """
    import traceback

    text = "".join(traceback.format_exception(exc))
    for stream in (sys.stderr, sys.stdout):
        if stream is not None:
            print(text, file=stream, end="")
            return


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        try:
            run_self_test()
        except BaseException as exc:  # noqa: BLE001 - 自检要覆盖断言失败和环境异常
            report_self_test_failure(exc)
            sys.exit(1)
    else:
        main()
