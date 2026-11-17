# -*- coding: utf-8 -*-
"""Local-only, text-only export for the current user's WeChat 4.x database."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path


BASE = Path(__file__).resolve().parent
VENDOR = BASE / "wechat_db.py"
VENDOR_SHA256 = "196bc986699cc0dab09967c4bc2e34d6891df74feaf80162c039f664585c2e4c"
TABLE_RE = re.compile(r"Msg_([0-9a-fA-F]{32})")
GROUP_SENDER_PREFIX_RE = re.compile(r"^([^:\r\n]{1,128}):\s*")


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def is_text_type(value: object) -> bool:
    return isinstance(value, int) and (value == 1 or value > 0xFFFF and value & 0xFF == 1)


def format_time(value: object) -> str:
    try:
        return datetime.fromtimestamp(timestamp_seconds(value)).astimezone().isoformat(timespec="seconds")
    except (OSError, OverflowError, TypeError, ValueError):
        return ""


def timestamp_seconds(value: object) -> float:
    timestamp = int(value)
    return timestamp / 1000 if timestamp > 10_000_000_000 else timestamp


def parse_time_bound(value: str, end_of_day: bool = False) -> float:
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("时间格式应为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]") from exc
    if end_of_day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        parsed = parsed.replace(hour=23, minute=59, second=59, microsecond=999999)
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return parsed.timestamp()


def in_time_range(value: object, start_time: float | None, end_time: float | None) -> bool:
    timestamp = timestamp_seconds(value)
    return (start_time is None or timestamp >= start_time) and (
        end_time is None or timestamp <= end_time
    )


def format_txt_message(
    time_text: str, chat_name: str, chat_id: str, sender: str, text: str
) -> str:
    return (
        f"[{time_text}] 会话：{chat_name}（{chat_id}） | 发送者：{sender}\n"
        f"{text}\n\n"
    )


def load_vendor():
    if hashlib.sha256(VENDOR.read_bytes()).hexdigest() != VENDOR_SHA256:
        raise RuntimeError("wechat_db.py 与已审计版本不一致，拒绝运行")
    spec = importlib.util.spec_from_file_location("audited_wechat_db", VENDOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 wechat_db.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sqlite_text_factory(data: bytes):
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data


class DecryptedWeChatDB:
    """Minimal read-only adapter for plaintext WeChat 4.x database copies."""

    def __init__(self, root: Path, account: str | None = None):
        self.root = root.resolve()
        self.account = account or self.root.name
        self.wxid = re.sub(r"_\w{4}$", "", self.account)
        self._db_files = []
        for path in sorted(self.root.rglob("*.db")):
            try:
                with path.open("rb") as handle:
                    if handle.read(16) != b"SQLite format 3\x00":
                        continue
            except OSError:
                continue
            self._db_files.append((
                os.path.relpath(path, self.root), str(path), path.stat().st_size,
            ))
        if not self._message_dbs():
            raise RuntimeError("--decrypted-root 中未找到解密后的 message_N.db")
        if sum(os.path.basename(path) == "contact.db" for _, path, _ in self._db_files) > 1:
            raise RuntimeError("--decrypted-root 包含多个账号，请分别导出")

    def _open(self, rel: str) -> sqlite3.Connection:
        try:
            path = next(Path(path) for item_rel, path, _ in self._db_files if item_rel == rel)
        except StopIteration as exc:
            raise KeyError(rel) from exc
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.text_factory = sqlite_text_factory
        return conn

    def _message_dbs(self) -> list[str]:
        return sorted(
            rel for rel, _, _ in self._db_files
            if re.search(r"(?:^|/)message_\d+\.db$", rel.replace("\\", "/"))
        )

    def _build_md5_index(self) -> dict[str, str]:
        index = {}
        for rel, path, _ in self._db_files:
            base = os.path.basename(path)
            if base not in ("contact.db", "session.db"):
                continue
            conn = self._open(rel)
            try:
                table = "contact" if base == "contact.db" else "SessionTable"
                for (username,) in conn.execute(f"SELECT username FROM {table}"):
                    if username:
                        index.setdefault(hashlib.md5(username.encode()).hexdigest(), username)
            except sqlite3.DatabaseError:
                pass
            finally:
                conn.close()
        return index

    def _nickname_index(self) -> dict[str, str]:
        for rel, path, _ in self._db_files:
            if os.path.basename(path) != "contact.db":
                continue
            conn = self._open(rel)
            try:
                return {
                    username: remark or nickname or username
                    for username, nickname, remark in conn.execute(
                        "SELECT username, nick_name, remark FROM contact"
                    )
                }
            except sqlite3.DatabaseError:
                return {}
            finally:
                conn.close()
        return {}

    def list_message_chats(self) -> list[dict]:
        tables = {}
        for rel in self._message_dbs():
            conn = self._open(rel)
            try:
                for (table,) in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                ):
                    try:
                        count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                    except sqlite3.DatabaseError:
                        continue
                    md5 = table[4:].lower()
                    tables[md5] = tables.get(md5, 0) + count
            finally:
                conn.close()
        usernames = self._build_md5_index()
        nicknames = self._nickname_index()
        chats = [
            {
                "md5": md5,
                "username": usernames.get(md5, md5),
                "name": nicknames.get(usernames.get(md5, md5), usernames.get(md5, md5)),
                "message_count": count,
            }
            for md5, count in tables.items()
        ]
        return sorted(chats, key=lambda chat: -chat["message_count"])

    @staticmethod
    def _friendly_content(content: bytes, _kind: str) -> str:
        for offset in range(min(16, len(content))):
            chunk = content[offset:].split(b"\x01\x00", 1)[0].rstrip(b"\x00")
            try:
                text = chunk.decode("utf-8")
            except UnicodeDecodeError:
                continue
            text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+", "", text).strip()
            if text and sum(char.isprintable() for char in text) / len(text) >= 0.6:
                return text
        return "[文本]"


def find_weixin_pids(vendor):
    class ProcessEntry(vendor.ctypes.Structure):
        _fields_ = [
            ("dwSize", vendor.wintypes.DWORD),
            ("cntUsage", vendor.wintypes.DWORD),
            ("th32ProcessID", vendor.wintypes.DWORD),
            ("th32DefaultHeapID", vendor.ctypes.c_size_t),
            ("th32ModuleID", vendor.wintypes.DWORD),
            ("cntThreads", vendor.wintypes.DWORD),
            ("th32ParentProcessID", vendor.wintypes.DWORD),
            ("pcPriClassBase", vendor.wintypes.LONG),
            ("dwFlags", vendor.wintypes.DWORD),
            ("szExeFile", vendor.ctypes.c_wchar * 260),
        ]

    kernel32 = vendor.ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.restype = vendor.ctypes.c_void_p
    kernel32.Process32FirstW.restype = vendor.wintypes.BOOL
    kernel32.Process32NextW.restype = vendor.wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    if not snapshot or snapshot == vendor.ctypes.c_void_p(-1).value:
        return []
    try:
        entry = ProcessEntry()
        entry.dwSize = vendor.ctypes.sizeof(entry)
        found = []
        ok = kernel32.Process32FirstW(snapshot, vendor.ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() == "weixin.exe":
                found.append(int(entry.th32ProcessID))
            entry.dwSize = vendor.ctypes.sizeof(entry)
            ok = kernel32.Process32NextW(snapshot, vendor.ctypes.byref(entry))
        return found
    finally:
        kernel32.CloseHandle(snapshot)


def resolve_db_root(vendor, supplied: str | None) -> Path:
    detected = supplied or vendor.auto_detect_db_dir()
    if not detected:
        raise RuntimeError("未找到微信数据目录，请用 --db-root 手动指定")
    root = Path(detected).expanduser().resolve()
    if not root.is_dir():
        raise RuntimeError(f"微信数据目录不存在: {root}")
    return root


def resolve_chat_filters(chats: list[dict], selectors: list[str]) -> dict[str, dict]:
    selected = {}
    for selector in selectors:
        needle = selector.strip().casefold()
        if not needle:
            raise RuntimeError("--chat 不能为空")
        matches = [
            chat for chat in chats
            if needle in {
                str(chat.get("username", "")).casefold(),
                str(chat.get("name", "")).casefold(),
                str(chat.get("md5", "")).casefold(),
            }
        ]
        if not matches:
            raise RuntimeError(f"未找到会话: {selector}；请先运行 --list-chats")
        if len(matches) > 1:
            raise RuntimeError(f"会话名称不唯一: {selector}；请改用会话ID或MD5")
        selected[str(matches[0]["md5"]).lower()] = matches[0]
    return selected


def get_self_name(db) -> str:
    for rel, path, _ in db._db_files:
        if os.path.basename(path) != "contact.db":
            continue
        conn = db._open(rel)
        try:
            row = conn.execute(
                "SELECT nick_name FROM contact WHERE username=? LIMIT 1", (db.wxid,)
            ).fetchone()
            return (row[0] if row else "") or "我"
        finally:
            conn.close()
    return "我"


def resolve_sender(
    chat_id: str,
    sender_id: object,
    content: str,
    nicknames: dict[str, str],
    self_name: str,
) -> tuple[str, str]:
    if sender_id in (2, "2"):
        return self_name, content
    if chat_id.endswith("@chatroom"):
        match = GROUP_SENDER_PREFIX_RE.match(content)
        if match:
            username = match.group(1)
            return nicknames.get(username, username), content[match.end():]
        return f"成员#{sender_id}", content
    return nicknames.get(chat_id, chat_id), content


def export_text(
    vendor,
    db_root: Path | None,
    account: str | None,
    output: Path | None,
    output_format: str = "txt",
    chat_selectors: list[str] | None = None,
    list_chats: bool = False,
    start_time: float | None = None,
    end_time: float | None = None,
    decrypted_root: Path | None = None,
) -> dict:
    if account and Path(account).name != account:
        raise RuntimeError(f"账号目录名无效: {account}")
    if decrypted_root is None:
        if account and (db_root is None or not (db_root / account / "db_storage").is_dir()):
            raise RuntimeError(f"账号目录无效: {account}")
        if not find_weixin_pids(vendor):
            raise RuntimeError("未检测到 Weixin.exe；请先离线启动并登录微信")

        class NoKeyCacheWeChatDB(vendor.WeChatDB):
            def _find_weixin_pids(self):
                return find_weixin_pids(vendor)

            def _save_keys(self) -> None:
                pass

    temp_root = Path(tempfile.gettempdir()) / "prophet-wechat-export"
    temp_root.mkdir(parents=True, exist_ok=True)
    records = []
    unreadable = 0
    selected_account = account or ""
    available_chats = None

    with tempfile.TemporaryDirectory(prefix="decrypt-", dir=temp_root) as workdir:
        if decrypted_root is not None:
            db = DecryptedWeChatDB(decrypted_root, account)
        else:
            db = NoKeyCacheWeChatDB(
                db_dir=str(db_root),
                account=account,
                workdir=workdir,
                keys_file=str(Path(workdir) / "keys.json"),
            )
        selected_account = db.account
        if list_chats:
            available_chats = db.list_message_chats()
        else:
            selected_md5s = None
            if chat_selectors:
                selected_md5s = set(resolve_chat_filters(
                    db.list_message_chats(), chat_selectors
                ))
            chats = db._build_md5_index()
            nicknames = db._nickname_index()
            self_name = get_self_name(db)

            for rel in db._message_dbs():
                conn = db._open(rel)
                try:
                    tables = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'Msg_%'"
                    )
                    for (table,) in tables:
                        match = TABLE_RE.fullmatch(table)
                        if not match:
                            continue
                        chat_md5 = match.group(1).lower()
                        if selected_md5s is not None and chat_md5 not in selected_md5s:
                            continue
                        chat_id = chats.get(chat_md5, chat_md5)
                        chat_name = nicknames.get(chat_id, chat_id)
                        rows = conn.execute(
                            f"SELECT local_id, local_type, real_sender_id, create_time, "
                            f"message_content, sort_seq FROM {table} ORDER BY sort_seq, local_id"
                        )
                        for row in rows:
                            if not in_time_range(row["create_time"] or 0, start_time, end_time):
                                continue
                            if not is_text_type(row["local_type"]):
                                continue
                            content = row["message_content"]
                            if isinstance(content, bytes):
                                content = db._friendly_content(content, "文本")
                            if not isinstance(content, str) or not content.strip() or content == "[文本]":
                                unreadable += 1
                                continue
                            sender, content = resolve_sender(
                                str(chat_id), row["real_sender_id"], content,
                                nicknames, self_name,
                            )
                            content = content.strip()
                            if not content:
                                unreadable += 1
                                continue
                            records.append((
                                str(chat_name),
                                str(chat_id),
                                int(row["create_time"] or 0),
                                int(row["sort_seq"] or 0),
                                int(row["local_id"] or 0),
                                str(sender),
                                content,
                            ))
                finally:
                    conn.close()

    try:
        temp_root.rmdir()
    except OSError:
        pass

    if available_chats is not None:
        return {"account": selected_account, "available_chats": available_chats}

    # ponytail: in-memory sort is adequate for desktop histories; use an external merge if RAM becomes the limit.
    records.sort(key=lambda row: (row[0].casefold(), row[2], row[3], row[4]))
    if output is None:
        raise RuntimeError("缺少输出路径")
    output.parent.mkdir(parents=True, exist_ok=True)
    pending = Path(str(output) + ".tmp")
    exported_at = datetime.now().astimezone().isoformat(timespec="seconds")
    chat_count = len({row[1] for row in records})
    encoding = "utf-8" if output_format == "json" else "utf-8-sig"
    with pending.open("w", encoding=encoding, newline="") as handle:
        if output_format == "json":
            payload = {
                "schema": "wechat-text-export-v1",
                "account": selected_account,
                "exported_at": exported_at,
                "stats": {
                    "messages": len(records),
                    "chats": chat_count,
                    "unreadable": unreadable,
                },
                "messages": [
                    {
                        "time": format_time(created),
                        "chat": chat_name,
                        "chat_id": chat_id,
                        "sender": sender,
                        "text": text,
                    }
                    for chat_name, chat_id, created, _, _, sender, text in records
                ],
            }
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        elif output_format == "txt":
            handle.write(
                "微信文字聊天记录\n"
                f"账号：{selected_account}\n"
                f"导出时间：{exported_at}\n"
                f"消息数：{len(records)}\n"
                f"会话数：{chat_count}\n"
                + "=" * 60 + "\n\n"
            )
            for chat_name, chat_id, created, _, _, sender, text in records:
                handle.write(format_txt_message(
                    format_time(created), chat_name, chat_id, sender, text
                ))
        else:
            writer = csv.writer(handle)
            writer.writerow(("时间", "会话", "会话ID", "发送者", "文本"))
            for chat_name, chat_id, created, _, _, sender, text in records:
                writer.writerow((format_time(created), chat_name, chat_id, sender, text))
    os.replace(pending, output)
    return {
        "output": str(output),
        "account": selected_account,
        "format": output_format,
        "messages": len(records),
        "chats": chat_count,
        "unreadable": unreadable,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def self_test() -> None:
    assert is_text_type(1)
    assert is_text_type(0x10001)
    assert not is_text_type(3)
    assert not is_text_type("1")
    assert format_time("bad") == ""
    assert in_time_range(0, None, None)
    start = parse_time_bound("2026-09-08")
    end = parse_time_bound("2026-09-08", end_of_day=True)
    assert in_time_range(start, start, end)
    assert in_time_range(int(end * 1000), start, end)
    assert not in_time_range(start - 1, start, end)
    assert format_txt_message(
        "2026-08-29T15:00:00+08:00", "测试会话", "wxid_test", "发送者", "第一行\n第二行"
    ) == (
        "[2026-08-29T15:00:00+08:00] 会话：测试会话（wxid_test） | 发送者：发送者\n"
        "第一行\n第二行\n\n"
    )
    names = {
        "wxid_member": "群成员",
        "custom_member": "自定义账号成员",
        "wxid_contact": "联系人",
    }
    assert resolve_sender(
        "group@chatroom", 7, "wxid_member:\n群消息", names, "我"
    ) == ("群成员", "群消息")
    assert resolve_sender(
        "group@chatroom", 8, "custom_member: 群消息", names, "我"
    ) == ("自定义账号成员", "群消息")
    assert resolve_sender(
        "group@chatroom", 2, "主题: 自己发送", names, "我"
    ) == ("我", "主题: 自己发送")
    assert resolve_sender(
        "group@chatroom", 9, "无前缀", names, "我"
    ) == ("成员#9", "无前缀")
    assert resolve_sender(
        "wxid_contact", 12345, "私聊", names, "我"
    ) == ("联系人", "私聊")
    chats = [
        {"md5": "a" * 32, "username": "wxid_contact", "name": "联系人"},
        {"md5": "b" * 32, "username": "group@chatroom", "name": "测试群"},
        {"md5": "c" * 32, "username": "wxid_other", "name": "测试群"},
    ]
    assert set(resolve_chat_filters(chats, ["wxid_contact", "group@chatroom"])) == {
        "a" * 32, "b" * 32
    }
    assert set(resolve_chat_filters(chats, ["联系人", "b" * 32])) == {
        "a" * 32, "b" * 32
    }
    try:
        resolve_chat_filters(chats, ["测试群"])
    except RuntimeError as exc:
        assert "不唯一" in str(exc)
    else:
        raise AssertionError("重名会话必须拒绝")
    with tempfile.TemporaryDirectory(prefix="wechat-export-test-") as test_dir:
        root = Path(test_dir)
        (root / "contact").mkdir()
        (root / "message").mkdir()
        with closing(sqlite3.connect(root / "contact" / "contact.db")) as conn:
            conn.execute("CREATE TABLE contact(username TEXT, nick_name TEXT, remark TEXT)")
            conn.executemany(
                "INSERT INTO contact VALUES(?, ?, ?)",
                [("wxid_self", "本人", ""), ("wxid_contact", "联系人", "")],
            )
            conn.commit()
        table = "Msg_" + hashlib.md5(b"wxid_contact").hexdigest()
        with closing(sqlite3.connect(root / "message" / "message_0.db")) as conn:
            conn.execute(
                f"CREATE TABLE {table}(local_id INTEGER, local_type INTEGER, "
                "real_sender_id INTEGER, create_time INTEGER, message_content TEXT, "
                "sort_seq INTEGER)"
            )
            conn.execute(
                f"INSERT INTO {table} VALUES(1, 1, 7, 1700000000, '测试消息', 1)"
            )
            conn.commit()
        output = root / "test.json"
        result = export_text(
            None, None, "wxid_self_abcd", output, "json", ["wxid_contact"],
            decrypted_root=root,
        )
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert result["messages"] == 1
        assert payload["messages"][0]["sender"] == "联系人"
        assert payload["messages"][0]["text"] == "测试消息"
    if sys.platform == "win32":
        load_vendor()
    else:
        assert hashlib.sha256(VENDOR.read_bytes()).hexdigest() == VENDOR_SHA256


def main() -> None:
    configure_stdio()
    parser = argparse.ArgumentParser(description="跨平台、本地导出微信 4.x 文字聊天记录")
    parser.add_argument("--db-root", help="Windows：包含账号目录的加密数据库根目录")
    parser.add_argument("--decrypted-root", help="macOS/Linux：平台工具生成的解密数据库目录")
    parser.add_argument("--account", help="账号目录名；解密模式下可省略，仅影响账号标签和本人昵称")
    parser.add_argument("--chat", action="append", help="会话名称、会话ID或MD5；可重复指定")
    parser.add_argument("--start-time", help="起始消息时间（含），如 2026-01-01 或 2026-01-01 08:30")
    parser.add_argument("--end-time", help="结束消息时间（含）；只写日期时包含当天全部消息")
    parser.add_argument("--format", choices=("csv", "json", "txt"), default="txt", help="输出格式")
    parser.add_argument("--output", help="输出路径；相对路径以工具目录为基准")
    parser.add_argument("--list-accounts", action="store_true", help="列出本地账号目录后退出")
    parser.add_argument("--list-chats", action="store_true", help="列出可导出的联系人和群聊")
    parser.add_argument("--self-test", action="store_true", help="只验证脚本和已审计模块")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print("SELF_TEST_OK")
        return

    decrypted_root = None
    if args.decrypted_root:
        decrypted_root = Path(args.decrypted_root).expanduser().resolve()
        if not decrypted_root.is_dir():
            raise RuntimeError(f"解密数据库目录不存在: {decrypted_root}")
        if args.list_accounts:
            raise RuntimeError("--list-accounts 不适用于 --decrypted-root；请分别指定每个账号的解密目录")
        vendor = None
        db_root = None
    else:
        if sys.platform != "win32":
            raise RuntimeError("macOS/Linux 请先生成解密副本，再通过 --decrypted-root 指定目录")
        if sys.maxsize <= 2**32:
            raise RuntimeError("需要 64 位 Python；32 位进程无法读取 64 位微信内存")
        vendor = load_vendor()
        db_root = resolve_db_root(vendor, args.db_root)
    if args.list_accounts:
        for path in vendor._find_account_dirs(str(db_root)):
            print(Path(path).name)
        return

    if args.list_chats:
        result = export_text(
            vendor, db_root, args.account, None, list_chats=True,
            decrypted_root=decrypted_root,
        )
        print("会话ID\t名称\t消息数\tMD5")
        for chat in result["available_chats"]:
            values = (
                chat["username"], chat["name"], chat["message_count"], chat["md5"]
            )
            print("\t".join(str(value).replace("\t", " ").replace("\r", " ").replace("\n", " ") for value in values))
        print(f"CHATS={len(result['available_chats'])}")
        return

    try:
        start_time = parse_time_bound(args.start_time) if args.start_time else None
        end_time = parse_time_bound(args.end_time, end_of_day=True) if args.end_time else None
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    if start_time is not None and end_time is not None and start_time > end_time:
        raise RuntimeError("--start-time 不能晚于 --end-time")

    output = Path(args.output).expanduser() if args.output else (
        BASE / "output" / f"wechat-text-{datetime.now():%Y%m%d-%H%M%S}.{args.format}"
    )
    if not output.is_absolute():
        output = BASE / output
    result = export_text(
        vendor, db_root, args.account, output.resolve(), args.format, args.chat,
        start_time=start_time, end_time=end_time, decrypted_root=decrypted_root,
    )
    for key in ("output", "account", "format", "messages", "chats", "unreadable", "sha256"):
        print(f"{key.upper()}={result[key]}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR={exc}", file=sys.stderr)
        raise SystemExit(1)
