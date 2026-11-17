#!/usr/bin/env python3
"""只读提取 Windows、macOS 和 Linux NTQQ 本地文字聊天记录。

默认流程：发现 nt_msg.db -> 获取 16 字节密钥 ->
解密 NTQQ SQLCipher 页面并合并 WAL -> 导出 c2c/group 文字消息。
不会修改 QQ 文件，也不会把密钥或明文数据库写入磁盘。
"""

from __future__ import annotations

import argparse
import _sqlite3
import csv
import datetime as dt
import glob
import hashlib
import hmac
import json
import os
import re
import sqlite3
import struct
import sys
import tempfile
import time
from ctypes import wintypes
from ctypes.util import find_library
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

try:
    import ctypes
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except ImportError as exc:  # pragma: no cover - startup error path
    raise SystemExit("需要 cryptography：python -m pip install cryptography") from exc


HEADER_SIZE = 1024
PAGE_SIZE = 4096
KDF_ITER = 4000
RESERVE_SIZE = 48  # AES-CBC IV 16 + SHA1 HMAC 20，按 16 字节对齐
HMAC_SIZE = 20
LOCK_BYTE_OFFSET = 0x40000000 - HEADER_SIZE
LOCK_BYTE_PAGE = LOCK_BYTE_OFFSET // PAGE_SIZE + 1
ZERO_PAGE = b"\x00" * PAGE_SIZE
CHUNK_SIZE = 4 * 1024 * 1024
_PRINTABLE16 = re.compile(rb"(?=([\x20-\x7e]{16}))")
_HASH_KEY16 = re.compile(rb"(?=(#[\x20-\x7e]{15}))")
_STANDALONE_PRINTABLE16 = re.compile(
    rb"(?<![\x20-\x7e])([\x20-\x7e]{16})(?![\x20-\x7e])"
)


def _varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _field(number: int, payload: bytes) -> bytes:
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def _wire_fields(data: bytes) -> Iterator[tuple[int, int, bytes | int]]:
    """最小 protobuf wire decoder；只保留导出文字所需的字段。"""
    pos = 0
    while pos < len(data):
        tag = 0
        shift = 0
        while True:
            if pos >= len(data) or shift > 63:
                raise ValueError("protobuf varint 损坏")
            b = data[pos]
            pos += 1
            tag |= (b & 0x7F) << shift
            if b < 0x80:
                break
            shift += 7
        number, wire_type = tag >> 3, tag & 7
        if number == 0:
            raise ValueError("protobuf 字段号为 0")
        if wire_type == 0:
            value = 0
            shift = 0
            while True:
                if pos >= len(data) or shift > 63:
                    raise ValueError("protobuf varint 损坏")
                b = data[pos]
                pos += 1
                value |= (b & 0x7F) << shift
                if b < 0x80:
                    break
                shift += 7
            yield number, wire_type, value
        elif wire_type == 1:
            if pos + 8 > len(data):
                raise ValueError("protobuf fixed64 损坏")
            yield number, wire_type, data[pos:pos + 8]
            pos += 8
        elif wire_type == 2:
            length = 0
            shift = 0
            while True:
                if pos >= len(data) or shift > 63:
                    raise ValueError("protobuf 长度损坏")
                b = data[pos]
                pos += 1
                length |= (b & 0x7F) << shift
                if b < 0x80:
                    break
                shift += 7
            end = pos + length
            if end > len(data):
                raise ValueError("protobuf 字段越界")
            yield number, wire_type, data[pos:end]
            pos = end
        elif wire_type == 5:
            if pos + 4 > len(data):
                raise ValueError("protobuf fixed32 损坏")
            yield number, wire_type, data[pos:pos + 4]
            pos += 4
        else:
            raise ValueError(f"不支持的 protobuf wire type: {wire_type}")


def extract_text(blob: object) -> Optional[str]:
    """从 40800 MsgBody 中取出所有 45101 文本段。"""
    if blob is None:
        return None
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    if not isinstance(blob, (bytes, bytearray)):
        return None
    parts: list[str] = []

    def walk(data: bytes, depth: int = 0) -> None:
        if depth > 4:
            return
        try:
            fields = list(_wire_fields(data))
        except ValueError:
            return
        for number, wire_type, value in fields:
            if wire_type != 2 or not isinstance(value, bytes):
                continue
            if number == 45101:
                text = value.decode("utf-8", errors="replace")
                if text:
                    parts.append(text)
            elif number == 40800:
                walk(value, depth + 1)

    walk(bytes(blob))
    return "\n".join(parts) if parts else None


def _derive_keys(passphrase: bytes, salt: bytes) -> tuple[bytes, bytes]:
    enc_key = hashlib.pbkdf2_hmac("sha512", passphrase, salt, KDF_ITER, 32)
    mac_salt = bytes(value ^ 0x3A for value in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, 32)
    return enc_key, mac_key


def _verify_page(mac_key: bytes, page: bytes, page_number: int) -> bool:
    if len(page) != PAGE_SIZE:
        return False
    hmac_start = PAGE_SIZE - RESERVE_SIZE + 16
    data_start = 16 if page_number == 1 else 0
    actual = hmac.new(
        mac_key,
        page[data_start:hmac_start] + struct.pack("<I", page_number),
        "sha1",
    ).digest()
    return hmac.compare_digest(actual, page[hmac_start:hmac_start + HMAC_SIZE])


def _is_lock_byte_page(page: bytes, page_number: int) -> bool:
    return page_number == LOCK_BYTE_PAGE and page == ZERO_PAGE


def _configure_sqlite_lock_byte() -> None:
    fallback = {
        "win32": "sqlite3.dll",
        "darwin": "/usr/lib/libsqlite3.dylib",
    }.get(sys.platform, "libsqlite3.so.0")
    for name in dict.fromkeys(filter(None, (_sqlite3.__file__, find_library("sqlite3"), fallback))):
        try:
            control = ctypes.CDLL(name).sqlite3_test_control
            control.restype = ctypes.c_int
            control(11, ctypes.c_uint(LOCK_BYTE_OFFSET))  # SQLITE_TESTCTRL_PENDING_BYTE
            if control(11, ctypes.c_uint(0)) == LOCK_BYTE_OFFSET:
                return
        except (AttributeError, OSError):
            continue
    raise RuntimeError("当前 Python 的 SQLite 无法读取超过 1 GiB 的 NTQQ 数据库")


def _decrypt_page(enc_key: bytes, page: bytes, page_number: int) -> bytes:
    iv_start = PAGE_SIZE - RESERVE_SIZE
    iv = page[iv_start:iv_start + 16]
    ciphertext = page[16:iv_start] if page_number == 1 else page[:iv_start]
    decryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(ciphertext) + decryptor.finalize()
    if page_number == 1:
        return b"SQLite format 3\x00" + plain + b"\x00" * RESERVE_SIZE
    return plain + b"\x00" * RESERVE_SIZE


def _validate_db_file(path: Path) -> tuple[bytes, int]:
    try:
        size = path.stat().st_size
        with path.open("rb") as src:
            header = src.read(HEADER_SIZE)
            page = src.read(PAGE_SIZE)
    except OSError as exc:
        raise RuntimeError(f"无法读取数据库：{path}: {exc}") from exc
    if len(header) != HEADER_SIZE or header[:16] != b"SQLite header 3\x00":
        raise RuntimeError(f"不是 NTQQ 数据库（缺少 1024 字节自定义头）：{path}")
    if b"QQ_NT DB" not in header[:64]:
        raise RuntimeError(f"NTQQ 自定义头校验失败：{path}")
    body_size = size - HEADER_SIZE
    if body_size <= 0 or body_size % PAGE_SIZE:
        raise RuntimeError("数据库正在写入或文件不完整：剥离头部后不是 4096 字节对齐")
    if len(page) != PAGE_SIZE:
        raise RuntimeError("数据库第一页不完整")
    return page, body_size // PAGE_SIZE


def verify_key(path: Path, key: bytes) -> bool:
    page, _ = _validate_db_file(path)
    _, mac_key = _derive_keys(key, page[:16])
    return _verify_page(mac_key, page, 1)


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", errors="replace").strip()
    return str(value).strip()


def _id(value: object) -> str:
    return _text(value)


@dataclass
class _NameMaps:
    profiles: dict[str, str]
    groups: dict[str, str]
    members: dict[tuple[str, str], str]


@dataclass(frozen=True)
class _Filters:
    persons: frozenset[str]
    groups: frozenset[str]
    chats: frozenset[str]
    start_time: Optional[int] = None
    end_time: Optional[int] = None


@dataclass(frozen=True)
class _Message:
    msg_id: int
    timestamp: int
    direction: int
    chat_type: str
    chat_id: str
    chat_qq: str
    chat_uid: str
    chat_name: str
    speaker_qq: str
    speaker_uid: str
    speaker_name: str
    msg_type: int
    text: str

    @property
    def chat_key(self) -> tuple[str, str]:
        return self.chat_type, self.chat_id


if os.name == "nt":
    class _MBI(ctypes.Structure):
        _fields_ = [
            ("BaseAddress", ctypes.c_void_p),
            ("AllocationBase", ctypes.c_void_p),
            ("AllocationProtect", wintypes.DWORD),
            ("_pad1", wintypes.DWORD),
            ("RegionSize", ctypes.c_size_t),
            ("State", wintypes.DWORD),
            ("Protect", wintypes.DWORD),
            ("Type", wintypes.DWORD),
            ("_pad2", wintypes.DWORD),
        ]

    class _PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_void_p),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _K32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    _K32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _K32.CloseHandle.argtypes = [wintypes.HANDLE]
    _K32.CloseHandle.restype = wintypes.BOOL
    _K32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _K32.Process32FirstW.restype = wintypes.BOOL
    _K32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
    _K32.Process32NextW.restype = wintypes.BOOL
    _K32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _K32.OpenProcess.restype = wintypes.HANDLE
    _K32.VirtualQueryEx.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(_MBI), ctypes.c_size_t,
    ]
    _K32.VirtualQueryEx.restype = ctypes.c_size_t
    _K32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    _K32.ReadProcessMemory.restype = wintypes.BOOL


def _qq_pids() -> list[int]:
    if os.name != "nt":
        return []
    snapshot = _K32.CreateToolhelp32Snapshot(0x00000002, 0)
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return []
    pids = []
    try:
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        if not _K32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        while True:
            if entry.szExeFile.lower() == "qq.exe":
                pids.append(int(entry.th32ProcessID))
            if not _K32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        _K32.CloseHandle(snapshot)
    return pids


def _read_process(handle: wintypes.HANDLE, address: int, size: int) -> bytes:
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    ok = _K32.ReadProcessMemory(
        handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got)
    )
    return buf.raw[:got.value] if ok and got.value else b""


def _readable_regions(
    handle: wintypes.HANDLE, private_only: bool = False
) -> Iterator[tuple[int, int]]:
    address = 0
    while True:
        mbi = _MBI()
        if not _K32.VirtualQueryEx(
            handle, ctypes.c_void_p(address), ctypes.byref(mbi), ctypes.sizeof(mbi)
        ):
            return
        base = int(mbi.BaseAddress or 0)
        size = int(mbi.RegionSize or 0)
        protect = int(mbi.Protect or 0) & 0xFF
        readable = protect in {2, 4, 8, 0x20, 0x40, 0x80}
        is_private = int(mbi.Type) == 0x20000  # MEM_PRIVATE，通常包含 Node/V8 堆
        if int(mbi.State) == 0x1000 and readable and size and (not private_only or is_private):
            yield base, size
        next_address = base + size
        if next_address <= address:
            return
        address = next_address


def _scan_pid_for_key(pid: int, page: bytes, tested: set[bytes]) -> Optional[bytes]:
    handle = _K32.OpenProcess(0x0010 | 0x0400, False, pid)
    if not handle:
        return None
    try:
        # 精确的 16 字节字符串候选最少；格式不固定，再回退到 # 和任意可打印窗口。
        for private_only, pattern in (
            (True, _STANDALONE_PRINTABLE16),
            (False, _STANDALONE_PRINTABLE16),
            (True, _HASH_KEY16),
            (False, _HASH_KEY16),
            (True, _PRINTABLE16),
            (False, _PRINTABLE16),
        ):
            for base, size in _readable_regions(handle, private_only):
                carry = b""
                for offset in range(0, size, CHUNK_SIZE):
                    chunk = _read_process(handle, base + offset, min(CHUNK_SIZE, size - offset))
                    if not chunk:
                        carry = b""
                        continue
                    data = carry + chunk
                    for match in pattern.finditer(data):
                        candidate = match.group(1)
                        if candidate in tested:
                            continue
                        tested.add(candidate)
                        if verify_key_bytes(page, candidate):
                            return candidate
                    carry = data[-16:]
    finally:
        _K32.CloseHandle(handle)
    return None


def verify_key_bytes(page: bytes, key: bytes) -> bool:
    if len(key) != 16 or any(value < 32 or value > 126 for value in key):
        return False
    _, mac_key = _derive_keys(key, page[:16])
    return _verify_page(mac_key, page, 1)


def find_key(path: Path, requested_pid: Optional[int] = None) -> bytes:
    if sys.platform != "win32":
        platform_name = "macOS" if sys.platform == "darwin" else "Linux"
        raise RuntimeError(
            f"{platform_name} 不自动读取 QQ 进程内存；请用 --key 或 --key-file 提供密钥"
        )
    if struct.calcsize("P") != 8:
        raise RuntimeError("自动提取密钥需要 64 位 Windows Python")
    page, _ = _validate_db_file(path)
    pids = [requested_pid] if requested_pid else _qq_pids()
    if not pids:
        raise RuntimeError("没有找到 QQ.exe；请先登录目标 QQ，再重试")
    tested: set[bytes] = set()
    for pid in pids:
        print(f"只读扫描 QQ.exe PID {pid} 内存…", file=sys.stderr)
        key = _scan_pid_for_key(pid, page, tested)
        if key:
            return key
    raise RuntimeError(
        "自动扫描未找到密钥；请保持目标账号已登录，或用 --key '16字节密钥' 重试"
    )


def _decrypt_file(
    src_path: Path, dst_path: Path, recover: bool = False
) -> tuple[bytes, bytes, int, list[int]]:
    page1, page_count = _validate_db_file(src_path)
    enc_key, mac_key = _derive_keys(_KEY, page1[:16])
    initial_stat = src_path.stat()
    bad_pages: list[int] = []
    with src_path.open("rb") as src, dst_path.open("wb") as dst:
        src.seek(HEADER_SIZE)
        for page_number in range(1, page_count + 1):
            page = src.read(PAGE_SIZE)
            if len(page) != PAGE_SIZE:
                raise RuntimeError("源数据库在读取过程中发生变化，请关闭 QQ 后重试")
            if _is_lock_byte_page(page, page_number):
                dst.write(page)
                continue
            if not _verify_page(mac_key, page, page_number):
                if recover and page_number > 1:
                    bad_pages.append(page_number)
                    dst.write(ZERO_PAGE)
                    continue
                raise RuntimeError(
                    f"第 {page_number} 页校验失败；请关闭 QQ 后重试，"
                    "若仍失败可加 --recover 导出可读取数据"
                )
            dst.write(_decrypt_page(enc_key, page, page_number))
    final_stat = src_path.stat()
    if (
        final_stat.st_size != initial_stat.st_size
        or final_stat.st_mtime_ns != initial_stat.st_mtime_ns
    ):
        raise RuntimeError("源数据库在读取过程中发生变化，请关闭 QQ 后重试")
    return enc_key, mac_key, page_count, bad_pages


def _merge_wal(dst_path: Path, wal_path: Path, enc_key: bytes, mac_key: bytes) -> int:
    try:
        wal_size = wal_path.stat().st_size
    except OSError:
        return 0
    if wal_size < 32:
        return 0
    frame_size = 24 + PAGE_SIZE
    applied = 0
    with wal_path.open("rb") as wal, dst_path.open("r+b") as dst:
        header = wal.read(32)
        if len(header) != 32 or struct.unpack(">I", header[8:12])[0] != PAGE_SIZE:
            return 0
        salt = header[16:24]
        frames = (wal_size - 32) // frame_size
        max_page = 0
        for _ in range(frames):
            frame_header = wal.read(24)
            page = wal.read(PAGE_SIZE)
            if len(frame_header) != 24 or len(page) != PAGE_SIZE:
                break
            page_number = struct.unpack(">I", frame_header[:4])[0]
            if not page_number or frame_header[8:16] != salt:
                continue
            if not _verify_page(mac_key, page, page_number):
                continue
            dst.seek((page_number - 1) * PAGE_SIZE)
            dst.write(_decrypt_page(enc_key, page, page_number))
            max_page = max(max_page, page_number)
            applied += 1
        if max_page:
            dst.flush()
            dst.seek(0)
            page1 = dst.read(PAGE_SIZE)
            current = struct.unpack(">I", page1[28:32])[0]
            total = max(current, max_page)
            if total != current:
                dst.seek(28)
                dst.write(struct.pack(">I", total))
    return applied


def _db_uri(path: Path) -> str:
    return path.resolve().as_uri() + "?mode=ro"


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _time_text(value: object) -> str:
    timestamp = _int(value)
    if timestamp > 10**12:
        timestamp //= 1000
    if timestamp <= 0:
        return "时间未知"
    try:
        return dt.datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return "时间未知"


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _quoted_columns(names: list[str]) -> str:
    return ", ".join('"' + name + '"' for name in names)


def _load_profile_names(conn: sqlite3.Connection, maps: _NameMaps) -> None:
    table_names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'profile_info_v%'"
        )
    }
    for table in sorted(table_names):
        columns = _columns(conn, table)
        id_columns = [name for name in ("1000", "1002") if name in columns]
        if not id_columns or "20002" not in columns:
            continue
        selected = id_columns + ["20002"]
        if "20009" in columns:
            selected.insert(-1, "20009")
        query = f'SELECT {_quoted_columns(selected)} FROM "{table}"'
        for row in conn.execute(query):
            name = _text(row["20009"]) if "20009" in columns else ""
            name = name or _text(row["20002"])
            if not name or name == "0":
                continue
            for column in id_columns:
                value = _id(row[column])
                if value and value != "0":
                    maps.profiles[value] = name


def _load_group_names(conn: sqlite3.Connection, maps: _NameMaps) -> None:
    for table in ("group_list", "group_detail_info_ver1"):
        columns = _columns(conn, table)
        if "60007" not in columns:
            continue
        id_columns = [
            name for name in ("60001", "60221", "60002") if name in columns
        ]
        if not id_columns:
            continue
        selected = id_columns + ["60007"]
        query = f'SELECT {_quoted_columns(selected)} FROM "{table}"'
        for row in conn.execute(query):
            name = _text(row["60007"])
            if not name or name == "0":
                continue
            for column in id_columns:
                value = _id(row[column])
                if value and value != "0":
                    maps.groups[value] = name


def _load_group_members(conn: sqlite3.Connection, maps: _NameMaps) -> None:
    table = "group_member3"
    columns = _columns(conn, table)
    required = {"60001", "20002", "64003"}
    if not required <= columns:
        return
    id_columns = [name for name in ("1000", "1002") if name in columns]
    if not id_columns:
        return
    selected = ["60001"] + id_columns + ["20002", "64003"]
    query = f'SELECT {_quoted_columns(selected)} FROM "{table}"'
    for row in conn.execute(query):
        group_id = _id(row["60001"])
        name = _text(row["64003"]) or _text(row["20002"])
        if not group_id or not name or name == "0":
            continue
        for column in id_columns:
            member_id = _id(row[column])
            if member_id and member_id != "0":
                maps.members[(group_id, member_id)] = name


def _load_name_maps(db_path: Path) -> _NameMaps:
    """从同一 nt_db 目录的资料库加载昵称、备注、群名和群名片。"""
    maps = _NameMaps({}, {}, {})
    for filename, loaders in (
        ("profile_info.db", (_load_profile_names,)),
        ("group_info.db", (_load_group_names, _load_group_members)),
    ):
        source = db_path.with_name(filename)
        if not source.exists():
            continue
        tmp_path: Optional[Path] = None
        conn: Optional[sqlite3.Connection] = None
        try:
            fd, name = tempfile.mkstemp(prefix="qq_names_", suffix=".db")
            os.close(fd)
            tmp_path = Path(name)
            enc_key, mac_key, _, _ = _decrypt_file(source, tmp_path)
            wal = Path(str(source) + "-wal")
            if wal.exists():
                _merge_wal(tmp_path, wal, enc_key, mac_key)
            conn = sqlite3.connect(tmp_path)
            conn.row_factory = sqlite3.Row
            for loader in loaders:
                loader(conn, maps)
        except (OSError, RuntimeError, sqlite3.DatabaseError):
            # 辅助库缺失/版本变化不应阻断文字导出；此时回退到 QQ 号或 UID。
            continue
        finally:
            if conn is not None:
                conn.close()
            if tmp_path is not None:
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
    return maps


def _matches(
    chat_type: str,
    filters: _Filters,
    *values: str,
) -> bool:
    if not filters.persons and not filters.groups and not filters.chats:
        return True
    tokens = {value.casefold() for value in values if value}
    if filters.chats & tokens:
        return True
    if chat_type == "private" and filters.persons & tokens:
        return True
    if chat_type == "group" and filters.groups & tokens:
        return True
    return False


def _record_stream(
    conn: sqlite3.Connection,
    table: str,
    maps: _NameMaps,
    filters: _Filters,
    recover: bool = False,
    skipped_rows: Optional[list[int]] = None,
) -> Iterator[_Message]:
    required = {
        "40001", "40013", "40020", "40021", "40030", "40033", "40050", "40011", "40800",
    }
    table_sql = _quote_identifier(table)
    query = f'''SELECT
        "40001" AS msg_id, "40050" AS timestamp, "40013" AS direction,
        "40020" AS sender_uid, "40033" AS sender_qq,
        "40021" AS peer_uid, "40030" AS peer_qq,
        "40011" AS msg_type, "40800" AS blob
        FROM {table_sql}'''
    conditions: list[str] = []
    params: list[int] = []
    if filters.start_time is not None:
        conditions.append('"40050" >= ?')
        params.append(filters.start_time)
    if filters.end_time is not None:
        conditions.append('"40050" <= ?')
        params.append(filters.end_time)
    where_sql = " WHERE " + " AND ".join(conditions) if conditions else ""
    query += where_sql
    chat_type = "group" if table == "group_msg_table" else "private"
    active = conn
    index_conn: Optional[sqlite3.Connection] = None

    def reopen() -> None:
        nonlocal active
        active.close()
        active = sqlite3.connect(_db_uri(database_path), uri=True)
        active.row_factory = sqlite3.Row

    def iter_rows() -> Iterator[sqlite3.Row]:
        nonlocal index_conn
        if not recover:
            yield from active.execute(query, params)
            return

        index_conn = sqlite3.connect(_db_uri(database_path), uri=True)
        index_conn.row_factory = sqlite3.Row
        indexes = [
            row[1]
            for row in index_conn.execute(f"PRAGMA index_list({table_sql})")
        ]
        if not indexes:
            yield from active.execute(query, params)
            return
        index_sql = _quote_identifier(indexes[0])
        rowid_query = f"SELECT rowid FROM {table_sql} INDEXED BY {index_sql}{where_sql}"
        row_query = query + (" AND " if conditions else " WHERE ") + "rowid IN ({})"

        def fetch_rows(rowids: list[int]) -> list[sqlite3.Row]:
            try:
                marks = ",".join("?" for _ in rowids)
                return active.execute(
                    row_query.format(marks), [*params, *rowids]
                ).fetchall()
            except sqlite3.DatabaseError:
                reopen()
                if not recover:
                    raise
                if len(rowids) == 1:
                    if skipped_rows is not None:
                        skipped_rows.append(rowids[0])
                    return []
                middle = len(rowids) // 2
                return fetch_rows(rowids[:middle]) + fetch_rows(rowids[middle:])

        batch: list[int] = []
        for row in index_conn.execute(rowid_query, params):
            batch.append(row[0])
            if len(batch) == 1000:
                yield from fetch_rows(batch)
                batch = []
        if batch:
            yield from fetch_rows(batch)

    if recover:
        database_path = Path(
            conn.execute("PRAGMA database_list").fetchone()[2]
        )
    try:
        if not required <= _columns(active, table):
            return
        for row in iter_rows():
            timestamp = _int(row["timestamp"])
            msg_id = _int(row["msg_id"])
            chat_qq = _id(row["peer_qq"])
            chat_uid = _id(row["peer_uid"])
            chat_id = chat_qq or chat_uid or "unknown"
            if chat_type == "group":
                chat_name = maps.groups.get(chat_qq) or maps.groups.get(chat_uid) or f"群 {chat_id}"
            else:
                chat_name = maps.profiles.get(chat_qq) or maps.profiles.get(chat_uid) or f"QQ {chat_id}"
            if not _matches(
                chat_type, filters, chat_id, chat_qq, chat_uid, chat_name
            ):
                continue
            text = extract_text(row["blob"])
            if not text:
                continue
            speaker_qq = _id(row["sender_qq"])
            speaker_uid = _id(row["sender_uid"])
            speaker_name = ""
            if chat_type == "group":
                for group_id in (chat_qq, chat_uid):
                    for member_id in (speaker_qq, speaker_uid):
                        if group_id and member_id:
                            speaker_name = maps.members.get((group_id, member_id), "")
                            if speaker_name:
                                break
                    if speaker_name:
                        break
            speaker_name = (
                speaker_name
                or maps.profiles.get(speaker_qq, "")
                or maps.profiles.get(speaker_uid, "")
                or "未知用户"
            )
            yield _Message(
                msg_id=msg_id,
                timestamp=timestamp,
                direction=_int(row["direction"]),
                chat_type=chat_type,
                chat_id=chat_id,
                chat_qq=chat_qq,
                chat_uid=chat_uid,
                chat_name=chat_name,
                speaker_qq=speaker_qq,
                speaker_uid=speaker_uid,
                speaker_name=speaker_name,
                msg_type=_int(row["msg_type"]),
                text=text.replace("\r\n", "\n").replace("\r", "\n"),
            )
    finally:
        if index_conn is not None:
            index_conn.close()
        if active is not conn:
            active.close()


def _message_dict(message: _Message) -> dict[str, object]:
    return {
        "time": _time_text(message.timestamp),
        "chat": message.chat_name,
        "chat_id": message.chat_id,
        "sender": message.speaker_name,
        "text": message.text,
    }


def _account_name(db_path: Path) -> str:
    parts = db_path.parts
    for index, part in enumerate(parts):
        if part.casefold() == "nt_qq" and index:
            return parts[index - 1]
    return db_path.parent.parent.name or "unknown"


def _new_output_path(output_dir: Path, output_format: str) -> Path:
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = output_dir / f"qq-text-{stamp}.{output_format}"
    suffix = 1
    while path.exists():
        path = output_dir / f"qq-text-{stamp}-{suffix}.{output_format}"
        suffix += 1
    return path


def export_messages(
    db_path: Path,
    output_dir: Path,
    output_format: str,
    maps: _NameMaps,
    filters: _Filters,
    account: str,
    limit: Optional[int],
    recover: bool = False,
    skipped_rows: Optional[list[int]] = None,
) -> tuple[int, int, Path]:
    output_path = _new_output_path(output_dir, output_format)
    pending_path = Path(str(output_path) + ".tmp")
    try:
        records: list[_Message] = []
        for table in ("c2c_msg_table", "group_msg_table"):
            conn = sqlite3.connect(_db_uri(db_path), uri=True)
            conn.row_factory = sqlite3.Row
            try:
                records.extend(
                    _record_stream(
                        conn, table, maps, filters, recover, skipped_rows
                    )
                )
            finally:
                conn.close()
        # ponytail: desktop histories fit in RAM; restore external merge if RAM becomes the limit.
        records.sort(key=lambda message: (message.timestamp, message.msg_id))
        if limit is not None:
            del records[limit:]
        chat_keys = {message.chat_key for message in records}
        written = len(records)
        exported_at = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        encoding = "utf-8" if output_format == "json" else "utf-8-sig"
        with pending_path.open("w", encoding=encoding, newline="") as output:
            if output_format == "csv":
                writer = csv.writer(output, lineterminator="\n")
                writer.writerow(("时间", "会话", "会话ID", "发送者", "文本"))
                for message in records:
                    writer.writerow((
                        _time_text(message.timestamp), message.chat_name,
                        message.chat_id, message.speaker_name, message.text,
                    ))
            elif output_format == "txt":
                output.write(
                    "QQ文字聊天记录\n"
                    f"账号：{account}\n"
                    f"导出时间：{exported_at}\n"
                    f"消息数：{written}\n"
                    f"会话数：{len(chat_keys)}\n"
                    + "=" * 60 + "\n\n"
                )
                for message in records:
                    output.write(
                        f"[{_time_text(message.timestamp)}] 会话：{message.chat_name}"
                        f"（{message.chat_id}） | 发送者：{message.speaker_name}\n"
                        f"{message.text}\n\n"
                    )
            else:
                output.write(
                    "{\n"
                    '  "schema": "qq-text-export-v1",\n'
                    f'  "account": {json.dumps(account, ensure_ascii=False)},\n'
                    f'  "exported_at": {json.dumps(exported_at)},\n'
                    '  "stats": {\n'
                    f'    "messages": {written},\n'
                    f'    "chats": {len(chat_keys)}\n'
                    "  },\n"
                    '  "messages": [\n'
                )
                for index, message in enumerate(records):
                    if index:
                        output.write(",\n")
                    payload = json.dumps(
                        _message_dict(message), ensure_ascii=False, indent=2
                    )
                    output.write("\n".join(f"    {line}" for line in payload.splitlines()))
                if records:
                    output.write("\n")
                output.write("  ]\n}\n")
        os.replace(pending_path, output_path)
        return written, len(chat_keys), output_path
    finally:
        try:
            pending_path.unlink()
        except OSError:
            pass


def _default_db_patterns(home: Path, platform: str) -> list[Path]:
    if platform == "win32":
        profile = Path(os.environ.get("USERPROFILE") or home)
        return [profile / "Documents" / "Tencent Files" / "*" / "nt_qq" / "nt_db" / "nt_msg.db"]
    if platform == "darwin":
        return [
            home / "Library" / "Containers" / "com.tencent.qq" / "Data" / "Documents" / "nt_qq" / "nt_db" / "nt_msg.db",
            home / "Library" / "Application Support" / "QQ" / "nt_qq*" / "nt_db" / "nt_msg.db",
        ]
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return [
        config / "QQ" / "nt_qq*" / "nt_db" / "nt_msg.db",
        home / ".var" / "app" / "com.qq.QQ" / "config" / "QQ" / "nt_qq*" / "nt_db" / "nt_msg.db",
    ]


def _discover_db(explicit: Optional[str], root: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    if root:
        base = Path(root).expanduser().resolve()
        if base.is_file():
            candidates = [base]
        elif base.is_dir():
            candidates = sorted({path for path in base.rglob("nt_msg.db") if path.is_file()})
        else:
            raise RuntimeError(f"数据库根目录不存在：{base}")
    else:
        candidates = sorted({
            Path(item)
            for pattern in _default_db_patterns(Path.home(), sys.platform)
            for item in glob.glob(str(pattern))
        })
    if not candidates:
        hint = "--db-root" if root else "--db"
        raise RuntimeError(f"未找到 nt_msg.db，请用 {hint} 指定路径")
    if len(candidates) > 1:
        paths = "\n".join(f"  - {item}" for item in candidates)
        raise RuntimeError(f"发现多个 nt_msg.db，请用 --db 指定一个：\n{paths}")
    return candidates[0].resolve()


def _split_values(values: Optional[list[str]]) -> frozenset[str]:
    return frozenset(
        item.strip().casefold()
        for value in values or []
        for item in value.split(",")
        if item.strip()
    )


def _parse_time(value: Optional[str], end_of_day: bool = False) -> Optional[int]:
    if value is None:
        return None
    value = value.strip()
    try:
        moment = dt.datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"时间格式无效：{value!r}；请使用 YYYY-MM-DD 或 YYYY-MM-DD HH:MM[:SS]"
        ) from exc
    if end_of_day and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        moment += dt.timedelta(days=1)
        return int(moment.timestamp()) - 1
    return int(moment.timestamp())


def _read_key_text(key: Optional[str], key_file: Optional[str]) -> Optional[str]:
    if key and key_file:
        raise RuntimeError("--key 和 --key-file 只能选一个")
    if key_file:
        return Path(key_file).expanduser().read_text(encoding="utf-8-sig").strip()
    return key or os.environ.get("NTQQ_DB_KEY")


def _self_test() -> None:
    blob = _field(40800, _field(45101, "你好 QQ".encode()))
    assert extract_text(blob) == "你好 QQ"
    assert _STANDALONE_PRINTABLE16.search(b"\x00#1234567890abcde\x00").group(1) == (
        b"#1234567890abcde"
    )

    sample = _Message(
        msg_id=1, timestamp=0, direction=0, chat_type="private", chat_id="123456",
        chat_qq="123456", chat_uid="", chat_name="张三", speaker_qq="123456",
        speaker_uid="", speaker_name="张三", msg_type=1, text="你好",
    )
    assert _message_dict(sample) == {
        "time": "时间未知", "chat": "张三", "chat_id": "123456",
        "sender": "张三", "text": "你好",
    }

    with tempfile.TemporaryDirectory(prefix="qq_export_test_") as tmp_name:
        tmp_dir = Path(tmp_name)
        db_path = tmp_dir / "plain.db"
        conn = sqlite3.connect(db_path)
        schema = '''(
            "40001" INTEGER, "40050" INTEGER, "40013" INTEGER,
            "40020" TEXT, "40033" INTEGER, "40021" TEXT,
            "40030" INTEGER, "40011" INTEGER, "40800" BLOB
        )'''
        for table in ("c2c_msg_table", "group_msg_table"):
            conn.execute(f'CREATE TABLE "{table}" {schema}')
            conn.execute(f'CREATE INDEX "{table}_id" ON "{table}" ("40001")')
        conn.execute(
            'INSERT INTO "c2c_msg_table" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (2, 20, 0, "u_alice", 10001, "u_alice", 10001, 1,
             _field(40800, _field(45101, "稍后".encode()))),
        )
        conn.execute(
            'INSERT INTO "group_msg_table" VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (1, 10, 0, "u_bob", 10002, "g_test", 20001, 1,
             _field(40800, _field(45101, "更早".encode()))),
        )
        conn.commit()
        conn.close()
        maps = _NameMaps(
            {"10001": "Alice", "10002": "Bob"}, {"20001": "测试群"}, {}
        )
        empty = _Filters(frozenset(), frozenset(), frozenset())
        count, chats, path = export_messages(
            db_path, tmp_dir, "json", maps, empty, "test", None
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert (count, chats) == (2, 2)
        assert [item["text"] for item in payload["messages"]] == ["更早", "稍后"]
        selected = _Filters(frozenset({"alice"}), frozenset(), frozenset())
        count, chats, _ = export_messages(
            db_path, tmp_dir, "json", maps, selected, "test", None
        )
        assert (count, chats) == (1, 1)
        timed = _Filters(
            frozenset(), frozenset(), frozenset(), start_time=15, end_time=20
        )
        count, chats, path = export_messages(
            db_path, tmp_dir, "json", maps, timed, "test", None
        )
        assert (count, chats) == (1, 1)
        assert json.loads(path.read_text(encoding="utf-8"))["messages"][0]["text"] == "稍后"
        key_path = tmp_dir / "qq_key.txt"
        key_path.write_text("\ufeff#1234567890abcde\n", encoding="utf-8")
        assert _read_key_text(None, str(key_path)) == "#1234567890abcde"
        count, chats, _ = export_messages(
            db_path, tmp_dir, "json", maps, timed, "test", None, recover=True
        )
        assert (count, chats) == (1, 1)
        for output_format in ("txt", "csv"):
            count, chats, path = export_messages(
                db_path, tmp_dir, output_format, maps, empty, "test", None
            )
            assert (count, chats) == (2, 2)
            assert "更早" in path.read_text(encoding="utf-8-sig")

    passphrase = b"#1234567890abcde"
    salt = bytes(range(16))
    enc_key, mac_key = _derive_keys(passphrase, salt)
    plain_tail = b"demo" + b"\x00" * (PAGE_SIZE - RESERVE_SIZE - 16 - 4)
    iv = bytes(range(16, 32))
    encryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(plain_tail) + encryptor.finalize()
    page = salt + ciphertext + iv
    page += hmac.new(mac_key, page[16:] + struct.pack("<I", 1), "sha1").digest()
    page += b"\x00" * (PAGE_SIZE - len(page))
    assert verify_key_bytes(page, passphrase)
    assert _decrypt_page(enc_key, page, 1).startswith(b"SQLite format 3\x00demo")

    iv2 = bytes(range(32, 48))
    plain2 = b"page2" + b"\x00" * (PAGE_SIZE - RESERVE_SIZE - 5)
    encryptor = Cipher(algorithms.AES(enc_key), modes.CBC(iv2)).encryptor()
    ciphertext2 = encryptor.update(plain2) + encryptor.finalize()
    page2 = ciphertext2 + iv2
    page2 += hmac.new(mac_key, page2 + struct.pack("<I", 2), "sha1").digest()
    page2 += b"\x00" * (PAGE_SIZE - len(page2))
    assert _verify_page(mac_key, page2, 2)
    assert _decrypt_page(enc_key, page2, 2).startswith(b"page2")
    assert _is_lock_byte_page(ZERO_PAGE, 262144)
    assert not _is_lock_byte_page(ZERO_PAGE, 262145)
    assert not _is_lock_byte_page(b"\x01" + ZERO_PAGE[1:], 262144)
    assert _parse_time("1970-01-01T00:00:01+00:00") == 1
    assert _parse_time("2026-08-01", True) > _parse_time("2026-08-01")
    assert "nt_qq*" in str(_default_db_patterns(Path("/home/test"), "linux")[0])
    assert "com.tencent.qq" in str(_default_db_patterns(Path("/Users/test"), "darwin")[0])
    _configure_sqlite_lock_byte()
    print("self-test ok")


_KEY = b""


def main() -> int:
    parser = argparse.ArgumentParser(description="只读导出 Windows、macOS 和 Linux NTQQ 文字聊天记录")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--db", help="直接指定 nt_msg.db 路径")
    source.add_argument("--db-root", help="指定数据库根目录；会递归寻找 nt_msg.db")
    parser.add_argument(
        "--output-dir", "--output", dest="output_dir", default="output",
        help="输出目录（默认 output；每次运行生成一个汇总文件）",
    )
    parser.add_argument(
        "--format", choices=("txt", "json", "csv"), default="txt",
        help="输出格式；每次运行一个文件（默认 txt）",
    )
    parser.add_argument("--person", action="append", help="只导出指定私聊对象，可重复或用逗号分隔")
    parser.add_argument("--group", action="append", help="只导出指定群，可重复或用逗号分隔")
    parser.add_argument("--chat", action="append", help="按 QQ号、UID 或聊天名称筛选，可重复或用逗号分隔")
    parser.add_argument(
        "--start-time", help="只导出此时间之后（含）的消息，如 2026-08-01 或 '2026-08-01 09:00'"
    )
    parser.add_argument(
        "--end-time", help="只导出此时间之前（含）的消息；只写日期时包含当天全天"
    )
    parser.add_argument("--key", help="16 字节 ASCII 数据库密钥；Windows 不提供时自动扫描 QQ.exe")
    parser.add_argument("--key-file", help="从文本文件读取 16 字节 ASCII 数据库密钥")
    parser.add_argument("--pid", type=int, help="Windows：只扫描指定 QQ.exe PID")
    parser.add_argument("--limit", type=int, help="最多输出多少条，用于先验收")
    parser.add_argument(
        "--recover",
        action="store_true",
        help="允许跳过校验失败页和无法读取的消息，尽量导出可读内容",
    )
    parser.add_argument("--self-test", action="store_true", help="运行内置自检")
    args = parser.parse_args()
    if args.self_test:
        _self_test()
        return 0
    if args.limit is not None and args.limit < 1:
        parser.error("--limit 必须大于 0")
    try:
        start_time = _parse_time(args.start_time)
        end_time = _parse_time(args.end_time, end_of_day=True)
    except ValueError as exc:
        parser.error(str(exc))
    if start_time is not None and end_time is not None and start_time > end_time:
        parser.error("--start-time 不能晚于 --end-time")

    global _KEY
    try:
        db_path = _discover_db(args.db, args.db_root)
        page, page_count = _validate_db_file(db_path)
        if page_count >= LOCK_BYTE_PAGE:
            _configure_sqlite_lock_byte()
        raw_key = _read_key_text(args.key, args.key_file)
        if raw_key:
            _KEY = raw_key.encode("ascii")
            if not verify_key_bytes(page, _KEY):
                raise RuntimeError("提供的密钥无法通过 nt_msg.db 第 1 页 HMAC 校验")
        else:
            _KEY = find_key(db_path, args.pid)

        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        filters = _Filters(
            persons=_split_values(args.person),
            groups=_split_values(args.group),
            chats=_split_values(args.chat),
            start_time=start_time,
            end_time=end_time,
        )
        maps = _load_name_maps(db_path)
        tmp_fd, tmp_name = tempfile.mkstemp(prefix="qq_plain_", suffix=".db")
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        applied = 0
        bad_pages: list[int] = []
        skipped_rows: list[int] = []
        try:
            for attempt in range(3):
                try:
                    enc_key, mac_key, _, bad_pages = _decrypt_file(
                        db_path, tmp_path, args.recover
                    )
                    wal = Path(str(db_path) + "-wal")
                    applied = _merge_wal(tmp_path, wal, enc_key, mac_key) if wal.exists() else 0
                    break
                except RuntimeError:
                    if attempt == 2:
                        raise
                    time.sleep(0.25)
            count, chats, output_path = export_messages(
                tmp_path, output_dir, args.format, maps, filters,
                _account_name(db_path), args.limit, args.recover, skipped_rows,
            )
        finally:
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if bad_pages:
            print(
                f"警告：恢复模式跳过 {len(bad_pages)} 个校验失败页 "
                f"（示例：{', '.join(map(str, bad_pages[:8]))}）",
                file=sys.stderr,
            )
        if skipped_rows:
            print(
                f"警告：恢复模式跳过 {len(skipped_rows)} 条无法读取的消息",
                file=sys.stderr,
            )
        print(f"完成：{count:,} 条文字消息，{chats} 个会话 -> {output_path}")
        print(f"数据库：{db_path}；格式：{args.format}；WAL 合并页：{applied}")
        return 0
    except (OSError, UnicodeEncodeError, RuntimeError, sqlite3.DatabaseError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
