"""Native file and directory dialogs used by the local web page."""

from __future__ import annotations

from typing import Any, Sequence


class DialogApiMixin:
    def _dialog(
        self,
        dialog_type: int,
        *,
        initial_dir: str = "",
        allow_multiple: bool = False,
        file_types: Sequence[str] = (),
    ) -> dict[str, Any]:
        if self._window is None:
            return self._error("WINDOW_NOT_READY", "窗口尚未准备好。")
        if not isinstance(initial_dir, str):
            return self._error("DIALOG_INPUT_INVALID", "文件对话框参数无效。")
        if not isinstance(allow_multiple, bool):
            return self._error("DIALOG_INPUT_INVALID", "文件对话框参数无效。")
        if not isinstance(file_types, (list, tuple)) or any(
            not isinstance(item, str) for item in file_types
        ):
            return self._error("DIALOG_INPUT_INVALID", "文件类型参数无效。")
        try:
            directory = self._resolve_directory(
                initial_dir or str(self.app_home), "初始目录"
            )
            if not directory.is_dir():
                directory = self.app_home
            selected = self._window.create_file_dialog(
                dialog_type,
                directory=str(directory),
                allow_multiple=allow_multiple,
                file_types=tuple(file_types),
            )
            paths = [str(path) for path in (selected or ())]
            return self._ok({"cancelled": not paths, "paths": paths})
        except (OSError, TypeError, ValueError) as error:
            return self._error("DIALOG_FAILED", str(error))

    def choose_file(
        self,
        initial_dir: str = "",
        file_types: Sequence[str] = (),
        allow_multiple: bool = False,
    ) -> dict[str, Any]:
        from webview import FileDialog

        return self._dialog(
            FileDialog.OPEN,
            initial_dir=initial_dir,
            file_types=file_types,
            allow_multiple=allow_multiple,
        )

    def choose_directory(self, initial_dir: str = "") -> dict[str, Any]:
        from webview import FileDialog

        return self._dialog(FileDialog.FOLDER, initial_dir=initial_dir)

