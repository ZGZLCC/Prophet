#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import heapq
import html
import json
import math
import os
import re
import shutil
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


VERSION = "1.2.2"
SENTINEL = ".chat-material-extractor-work"
SESSION_GAP_SECONDS = 60 * 60
CHUNK_MESSAGE_LIMIT = 80
CHUNK_OVERLAP = 10
CHUNK_CHAR_LIMIT = 15_000
SAMPLE_RATIO = 0.20
MAX_MESSAGES_PER_PERIOD = 20_000
SHORT_MESSAGE_LIMIT = 6
SORT_BATCH_SIZE = 50_000
MATERIAL_TYPES = {"language", "emotion", "interaction", "conflict", "support", "event"}
GENERIC_DIMENSIONS = {
    "语言", "情绪", "互动", "冲突", "支持", "事件", "行为模式",
    "沟通方式", "沟通表达", "情绪表达", "互动模式", "冲突处理", "支持方式",
}
PUNCTUATION = "，。！？!?…~～、；;：:"
VALUE_KEYWORDS = (
    "开心", "高兴", "难过", "伤心", "生气", "烦", "累", "压力", "紧张", "害怕",
    "吵", "别说", "不想说", "算了", "误会", "冷静", "对不起", "抱歉", "谢谢",
    "加油", "没事", "陪你", "帮你", "支持", "考试", "作业", "工作", "加班",
    "见面", "出行", "医院", "生日", "纪念日", "分手",
)
QUERY_EXPANSIONS = {
    "冲突": ("冲突", "吵", "生气", "不满", "误会", "冷淡", "算了", "别说", "道歉"),
    "生气": ("生气", "烦", "火大", "不爽", "气死", "别说", "算了"),
    "支持": ("支持", "加油", "没事", "陪你", "帮你", "安慰", "建议"),
    "情绪": ("开心", "高兴", "难过", "伤心", "生气", "烦", "累", "紧张", "害怕"),
    "事件": ("考试", "作业", "工作", "加班", "见面", "出行", "医院", "生日", "纪念日"),
}


class ExtractorError(Exception):
    pass


def json_text(value: Any, *, pretty: bool = False) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2 if pretty else None)


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8", newline="\n")
    temporary.replace(path)


def write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json_text(value, pretty=True) + "\n")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ExtractorError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ExtractorError(f"JSON 无效：{path}（{exc}）") from exc


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ExtractorError(f"{path} 第 {line_number} 行不是有效 JSON") from exc
                if not isinstance(value, dict):
                    raise ExtractorError(f"{path} 第 {line_number} 行必须是 JSON 对象")
                yield value
    except FileNotFoundError as exc:
        raise ExtractorError(f"找不到工作文件：{path}") from exc


def write_jsonl_atomic(path: Path, records: Iterable[dict[str, Any]]) -> None:
    atomic_write_text(path, "".join(json_text(record) + "\n" for record in records))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_time(value: Any, *, where: str = "time") -> tuple[datetime, float, str]:
    if not isinstance(value, str) or not value.strip():
        raise ExtractorError(f"{where} 必须是非空 ISO 8601 字符串")
    raw = value.strip()
    normalized = raw[:-1] + "+00:00" if raw.endswith(("Z", "z")) else raw
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ExtractorError(f"{where} 无法解析：{raw}") from exc
    aware = parsed.tzinfo is not None and parsed.utcoffset() is not None
    if aware:
        stamp = (parsed.astimezone(timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds()
        mode = "aware"
    else:
        stamp = (parsed - datetime(1970, 1, 1)).total_seconds()
        mode = "naive"
    return parsed, stamp, mode


def iter_json_records(path: Path) -> Iterator[Any]:
    decoder = json.JSONDecoder()
    with path.open("r", encoding="utf-8-sig") as handle:
        buffer = ""
        position = 0
        eof = False

        def read_more() -> bool:
            nonlocal buffer, position, eof
            if eof:
                return False
            if position:
                buffer = buffer[position:]
                position = 0
            chunk = handle.read(64 * 1024)
            if chunk:
                buffer += chunk
                return True
            eof = True
            return False

        def skip_space() -> bool:
            nonlocal position
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer):
                    return True
                if not read_more():
                    return False

        def decode_one() -> Any:
            nonlocal position
            while True:
                try:
                    value, end = decoder.raw_decode(buffer, position)
                    position = end
                    return value
                except json.JSONDecodeError as exc:
                    if eof or not read_more():
                        raise ExtractorError(f"聊天文件不是有效 JSON：{exc}") from exc

        if not skip_space():
            raise ExtractorError("聊天文件为空")

        if buffer[position] == "[":
            position += 1
            first = True
            while True:
                if not skip_space():
                    raise ExtractorError("JSON 数组缺少结束符 ]")
                if buffer[position] == "]":
                    position += 1
                    if skip_space():
                        raise ExtractorError("JSON 数组结束后存在额外内容")
                    return
                if not first:
                    if buffer[position] != ",":
                        raise ExtractorError("JSON 数组元素之间缺少逗号")
                    position += 1
                    if not skip_space():
                        raise ExtractorError("JSON 数组在逗号后意外结束")
                yield decode_one()
                first = False
        else:
            while True:
                value = decode_one()
                if isinstance(value, dict) and isinstance(value.get("messages"), list):
                    yield from value["messages"]
                else:
                    yield value
                if not skip_space():
                    return


def input_sender_counts(path: Path) -> dict[str, int]:
    counts: Counter[str] = Counter()
    valid = 0
    skipped = 0
    for index, record in enumerate(iter_json_records(path), 1):
        if not isinstance(record, dict):
            raise ExtractorError(f"第 {index} 条记录必须是 JSON 对象")
        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            skipped += 1
            continue
        sender = record.get("sender")
        if not isinstance(sender, str) or not sender.strip():
            raise ExtractorError(f"第 {index} 条文字消息缺少 sender")
        counts[sender.strip()] += 1
        valid += 1
    return {"valid_text_messages": valid, "skipped_records": skipped, "senders": dict(counts)}


def flush_sorted_run(batch: list[dict[str, Any]], runs_dir: Path, number: int) -> Path:
    batch.sort(key=lambda item: (item["_ts"], item["source_index"]))
    path = runs_dir / f"run_{number:06d}.jsonl"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in batch:
            handle.write(json_text(record) + "\n")
    batch.clear()
    return path


def iter_handle_jsonl(handle: Any) -> Iterator[dict[str, Any]]:
    for line in handle:
        if line.strip():
            yield json.loads(line)


def normalize_messages(input_path: Path, work_dir: Path, target: str) -> dict[str, Any]:
    runs_dir = work_dir / "sort-runs"
    runs_dir.mkdir()
    run_paths: list[Path] = []
    batch: list[dict[str, Any]] = []
    participant_counts: Counter[str] = Counter()
    raw_count = 0
    skipped_count = 0
    time_mode: str | None = None
    chat_name: Any = None
    chat_id: Any = None

    for source_index, record in enumerate(iter_json_records(input_path), 1):
        raw_count += 1
        if not isinstance(record, dict):
            raise ExtractorError(f"第 {source_index} 条记录必须是 JSON 对象")
        if chat_name is None and record.get("chat") is not None:
            chat_name = record.get("chat")
        if chat_id is None and record.get("chat_id") is not None:
            chat_id = record.get("chat_id")

        text = record.get("text")
        if not isinstance(text, str) or not text.strip():
            skipped_count += 1
            continue
        sender = record.get("sender")
        if not isinstance(sender, str) or not sender.strip():
            raise ExtractorError(f"第 {source_index} 条文字消息缺少 sender")
        parsed, stamp, current_mode = parse_time(record.get("time"), where=f"第 {source_index} 条记录的 time")
        if time_mode is None:
            time_mode = current_mode
        elif time_mode != current_mode:
            raise ExtractorError("聊天记录混用了带时区和不带时区的时间，无法可靠排序")

        sender = sender.strip()
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        participant_counts[sender] += 1
        batch.append(
            {
                "_ts": stamp,
                "source_index": source_index,
                "time": parsed.isoformat(),
                "sender": sender,
                "text": normalized_text,
            }
        )
        if len(batch) >= SORT_BATCH_SIZE:
            run_paths.append(flush_sorted_run(batch, runs_dir, len(run_paths) + 1))

    if batch:
        run_paths.append(flush_sorted_run(batch, runs_dir, len(run_paths) + 1))
    if not run_paths:
        raise ExtractorError("没有可分析的文字消息")
    if len(participant_counts) > 2:
        raise ExtractorError(f"发现 {len(participant_counts)} 个 sender；V1.2 只支持双人聊天")
    if target not in participant_counts:
        available = "、".join(participant_counts)
        raise ExtractorError(f"目标人物 {target!r} 不在聊天中；可选 sender：{available}")

    output_path = work_dir / "messages.jsonl"
    handles = [path.open("r", encoding="utf-8") for path in run_paths]
    first_time: str | None = None
    last_time: str | None = None
    valid_count = 0
    try:
        merged = heapq.merge(
            *(iter_handle_jsonl(handle) for handle in handles),
            key=lambda item: (item["_ts"], item["source_index"]),
        )
        with output_path.open("w", encoding="utf-8", newline="\n") as output:
            for valid_count, message in enumerate(merged, 1):
                message["id"] = f"msg_{valid_count:09d}"
                first_time = first_time or message["time"]
                last_time = message["time"]
                output.write(json_text(message) + "\n")
    finally:
        for handle in handles:
            handle.close()
        for path in run_paths:
            path.unlink(missing_ok=True)
        runs_dir.rmdir()

    return {
        "raw_record_count": raw_count,
        "valid_text_message_count": valid_count,
        "skipped_record_count": skipped_count,
        "participants": dict(participant_counts),
        "chat": chat_name,
        "chat_id": chat_id,
        "time_mode": time_mode,
        "start_time": first_time,
        "end_time": last_time,
    }


def period_for(time_text: str, kind: str) -> tuple[str, str]:
    parsed, _, _ = parse_time(time_text)
    if kind == "hour":
        key = parsed.strftime("%Y-%m-%dT%H")
        return key, parsed.strftime("%Y-%m-%d %H:00")
    if kind == "day":
        key = parsed.strftime("%Y-%m-%d")
        return key, key
    if kind == "week":
        start = parsed.date() - timedelta(days=parsed.weekday())
        end = start + timedelta(days=6)
        iso_year, iso_week, _ = parsed.isocalendar()
        key = f"{iso_year}-W{iso_week:02d}"
        return key, f"{key}（{start.isoformat()} 至 {end.isoformat()}）"
    key = f"{parsed.year:04d}-{parsed.month:02d}"
    return key, key


def phrase_candidates(text: str) -> Iterator[str]:
    for token in re.findall(r"[A-Za-z][A-Za-z0-9']+|[\u4e00-\u9fff]{2,}", text.lower()[:300]):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            for size in (2, 3):
                for index in range(max(0, len(token) - size + 1)):
                    yield token[index:index + size]
        elif len(token) >= 2:
            yield token


def trim_counter(counter: Counter[str], keep: int = 5_000, limit: int = 20_000) -> None:
    if len(counter) <= limit:
        return
    # ponytail: bounded approximate phrase counts; use an external counter only if measured recall is inadequate.
    retained = counter.most_common(keep)
    counter.clear()
    counter.update(dict(retained))


def chunk_score(messages: list[dict[str, Any]], target: str) -> tuple[float, dict[str, int]]:
    target_messages = [message for message in messages if message["sender"] == target]
    turns = sum(
        left["sender"] != right["sender"]
        for left, right in zip(messages, messages[1:])
    )
    joined = "\n".join(message["text"] for message in messages)
    keyword_hits = sum(joined.count(keyword) for keyword in VALUE_KEYWORDS)
    punctuation_hits = sum(joined.count(mark) for mark in "！？!?")
    score = (
        len(target_messages) * 1.0
        + turns * 0.75
        + min(sum(len(message["text"]) for message in messages) / 200, 10)
        + keyword_hits * 3
        + min(punctuation_hits, 10) * 0.5
    )
    return round(score, 3), {
        "target_messages": len(target_messages),
        "turns": turns,
        "keyword_hits": keyword_hits,
    }


def choose_period_chunks(items: list[dict[str, Any]]) -> dict[str, str]:
    if not items:
        return {}
    quota = max(1, math.ceil(len(items) * SAMPLE_RATIO))
    priority_count = (quota + 1) // 2
    chosen: dict[str, str] = {}
    for item in sorted(items, key=lambda value: (-value["score"], value["start_ts"], value["chunk_id"]))[:priority_count]:
        chosen[item["chunk_id"]] = "priority"

    uniform_count = quota - len(chosen)
    available = [item for item in items if item["chunk_id"] not in chosen]
    for index in range(uniform_count):
        if not available:
            break
        position = min(len(available) - 1, math.floor((index + 0.5) * len(available) / uniform_count))
        item = available.pop(position)
        chosen[item["chunk_id"]] = "time_coverage"

    if len(chosen) < quota:
        for item in sorted(items, key=lambda value: (-value["score"], value["start_ts"])):
            chosen.setdefault(item["chunk_id"], "priority")
            if len(chosen) == quota:
                break
    return chosen


def analyze_messages(work_dir: Path, target: str, normalized: dict[str, Any]) -> tuple[dict[str, Any], int, int]:
    _, start_stamp, _ = parse_time(normalized["start_time"])
    _, end_stamp, _ = parse_time(normalized["end_time"])
    span_seconds = max(1.0, end_stamp - start_stamp)
    span_days = max(1.0, span_seconds / (24 * 60 * 60))
    messages_per_day = normalized["valid_text_message_count"] / span_days
    if messages_per_day > MAX_MESSAGES_PER_PERIOD:
        period_kind = "hour"
    elif messages_per_day * 7 > MAX_MESSAGES_PER_PERIOD:
        period_kind = "day"
    elif span_seconds <= 31 * 24 * 60 * 60 or messages_per_day * 30 > MAX_MESSAGES_PER_PERIOD:
        period_kind = "week"
    else:
        period_kind = "month"

    message_counts: Counter[str] = Counter()
    period_counts: dict[str, Counter[str]] = defaultdict(Counter)
    period_labels: dict[str, str] = {}
    lengths: dict[str, list[int]] = defaultdict(list)
    short_counts: Counter[str] = Counter()
    active_hours: dict[str, Counter[int]] = defaultdict(Counter)
    punctuation_counts: dict[str, Counter[str]] = defaultdict(Counter)
    phrases: dict[str, Counter[str]] = defaultdict(Counter)
    session_starts: Counter[str] = Counter()
    reply_times: dict[str, list[float]] = defaultdict(list)
    run_lengths: dict[str, list[int]] = defaultdict(list)
    period_chunks: dict[str, list[dict[str, Any]]] = defaultdict(list)

    previous: dict[str, Any] | None = None
    run_sender: str | None = None
    run_length = 0
    session_count = 0
    session_id = 0
    chunk_number = 0
    chunk: list[dict[str, Any]] = []
    chunk_period: str | None = None
    chunk_session = 0
    chunks_path = work_dir / "chunks.jsonl"

    with chunks_path.open("w", encoding="utf-8", newline="\n") as chunk_output:
        def emit_chunk() -> None:
            nonlocal chunk_number, chunk
            if not chunk or chunk_period is None:
                return
            chunk_number += 1
            score, signals = chunk_score(chunk, target)
            record = {
                "chunk_id": f"chunk_{chunk_number:06d}",
                "period": chunk_period,
                "session_id": f"session_{chunk_session:06d}",
                "start_time": chunk[0]["time"],
                "end_time": chunk[-1]["time"],
                "start_ts": chunk[0]["_ts"],
                "end_ts": chunk[-1]["_ts"],
                "message_count": len(chunk),
                "target_message_count": signals["target_messages"],
                "score": score,
                "score_signals": signals,
                "messages": chunk,
            }
            chunk_output.write(json_text(record) + "\n")
            if signals["target_messages"]:
                period_chunks[chunk_period].append(
                    {
                        "chunk_id": record["chunk_id"],
                        "start_ts": record["start_ts"],
                        "score": score,
                    }
                )

        processed = 0
        for message in iter_jsonl(work_dir / "messages.jsonl"):
            processed += 1
            parsed, stamp, _ = parse_time(message["time"])
            period, period_label = period_for(message["time"], period_kind)
            period_labels.setdefault(period, period_label)
            sender = message["sender"]
            text = message["text"]
            message_counts[sender] += 1
            period_counts[period][sender] += 1
            lengths[sender].append(len(text))
            short_counts[sender] += len(text) <= SHORT_MESSAGE_LIMIT
            active_hours[sender][parsed.hour] += 1
            punctuation_counts[sender].update(character for character in text if character in PUNCTUATION)
            phrases[sender].update(phrase_candidates(text))
            if processed % 10_000 == 0:
                for counter in phrases.values():
                    trim_counter(counter)

            new_session = previous is None or stamp - previous["_ts"] >= SESSION_GAP_SECONDS
            if new_session:
                if run_sender is not None:
                    run_lengths[run_sender].append(run_length)
                session_count += 1
                session_id += 1
                session_starts[sender] += 1
                run_sender = sender
                run_length = 1
            elif sender == run_sender:
                run_length += 1
            else:
                if previous is not None and sender != previous["sender"]:
                    reply_times[sender].append(max(0.0, stamp - previous["_ts"]))
                if run_sender is not None:
                    run_lengths[run_sender].append(run_length)
                run_sender = sender
                run_length = 1

            period_boundary = chunk_period is not None and period != chunk_period
            if chunk and (new_session or period_boundary):
                emit_chunk()
                chunk = []

            chunk_period = period
            chunk_session = session_id
            text_size = len(text)
            current_size = sum(len(item["text"]) for item in chunk)
            if chunk and (len(chunk) >= CHUNK_MESSAGE_LIMIT or current_size + text_size > CHUNK_CHAR_LIMIT):
                emit_chunk()
                overlap = chunk[-CHUNK_OVERLAP:]
                if sum(len(item["text"]) for item in overlap) >= CHUNK_CHAR_LIMIT:
                    overlap = []
                chunk = overlap
            chunk.append(message)
            previous = message

        emit_chunk()

    if run_sender is not None:
        run_lengths[run_sender].append(run_length)

    selected: dict[str, str] = {}
    for period, items in period_chunks.items():
        selected.update(choose_period_chunks(items))

    tasks_path = work_dir / "tasks.jsonl"
    selected_per_period: Counter[str] = Counter()
    with tasks_path.open("w", encoding="utf-8", newline="\n") as tasks_output:
        for record in iter_jsonl(chunks_path):
            reason = selected.get(record["chunk_id"])
            if not reason:
                continue
            record["selection_reason"] = reason
            tasks_output.write(json_text(record) + "\n")
            selected_per_period[record["period"]] += 1

    participants = list(message_counts)
    stats_periods: list[dict[str, Any]] = []
    for period, counts in period_counts.items():
        if not counts[target]:
            continue
        candidate_count = len(period_chunks[period])
        stats_periods.append(
            {
                "period": period,
                "label": period_labels[period],
                "message_count": sum(counts.values()),
                "target_message_count": counts[target],
                "candidate_chunks": candidate_count,
                "selected_chunks": selected_per_period[period],
                "selection_ratio": round(selected_per_period[period] / candidate_count, 4) if candidate_count else 0,
            }
        )

    def sender_value(mapping: dict[str, list[Any]], sender: str, reducer: Any) -> Any:
        values = mapping.get(sender, [])
        return reducer(values) if values else None

    stats = {
        "period_kind": period_kind,
        "message_count": sum(message_counts.values()),
        "participants": dict(message_counts),
        "periods": stats_periods,
        "avg_message_length": {
            sender: round(statistics.fmean(lengths[sender]), 2) for sender in participants
        },
        "median_message_length": {
            sender: round(statistics.median(lengths[sender]), 2) for sender in participants
        },
        "short_message_ratio": {
            sender: round(short_counts[sender] / message_counts[sender], 4) for sender in participants
        },
        "session_count": session_count,
        "session_initiation": {
            sender: {
                "count": session_starts[sender],
                "ratio": round(session_starts[sender] / session_count, 4) if session_count else 0,
            }
            for sender in participants
        },
        "median_reply_seconds": {
            sender: sender_value(reply_times, sender, lambda values: round(statistics.median(values), 2))
            for sender in participants
        },
        "avg_consecutive_messages": {
            sender: sender_value(run_lengths, sender, lambda values: round(statistics.fmean(values), 2))
            for sender in participants
        },
        "max_consecutive_messages": {
            sender: sender_value(run_lengths, sender, max) for sender in participants
        },
        "active_hours": {
            sender: {str(hour): active_hours[sender][hour] for hour in range(24)}
            for sender in participants
        },
        "common_phrases": {
            sender: [{"text": text, "count": count} for text, count in phrases[sender].most_common(15)]
            for sender in participants
        },
        "punctuation": {
            sender: dict(punctuation_counts[sender].most_common()) for sender in participants
        },
        "definitions": {
            "short_message": f"字符数不超过 {SHORT_MESSAGE_LIMIT}",
            "session_gap": f"{SESSION_GAP_SECONDS // 60} 分钟",
            "chunk": f"最多 {CHUNK_MESSAGE_LIMIT} 条、重叠 {CHUNK_OVERLAP} 条、最多 {CHUNK_CHAR_LIMIT} 字符",
            "sampling": f"每个活跃时期 max(1, ceil(C × {int(SAMPLE_RATIO * 100)}%))",
            "phrases": "英文词与中文 2～3 字符短语；大规模数据使用有界近似计数",
        },
    }
    write_json(work_dir / "statistics.json", stats)
    (work_dir / "annotations.jsonl").write_text("", encoding="utf-8")
    (work_dir / "period-summaries.jsonl").write_text("", encoding="utf-8")
    return stats, chunk_number, len(selected)


def create_manifest(
    input_path: Path,
    input_hash: str,
    work_dir: Path,
    target: str,
    normalized: dict[str, Any],
    stats: dict[str, Any],
    chunk_count: int,
    task_count: int,
) -> dict[str, Any]:
    return {
        "version": VERSION,
        "input_name": input_path.name,
        "input_path": str(input_path),
        "input_sha256": input_hash,
        "target": target,
        "chat": normalized.get("chat"),
        "chat_id": normalized.get("chat_id"),
        "start_time": normalized["start_time"],
        "end_time": normalized["end_time"],
        "raw_record_count": normalized["raw_record_count"],
        "valid_text_message_count": normalized["valid_text_message_count"],
        "skipped_record_count": normalized["skipped_record_count"],
        "participants": normalized["participants"],
        "period_kind": stats["period_kind"],
        "chunk_count": chunk_count,
        "task_count": task_count,
        "work_dir": str(work_dir),
    }


def ensure_work_dir(work_dir: Path) -> dict[str, Any]:
    if not (work_dir / SENTINEL).is_file():
        raise ExtractorError(f"{work_dir} 不是本工具创建的工作目录")
    manifest_path = work_dir / "manifest.json"
    if not manifest_path.is_file():
        raise ExtractorError(f"{work_dir} 尚未准备完成")
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict):
        raise ExtractorError("manifest.json 格式无效")
    return manifest


def update_state(work_dir: Path) -> None:
    manifest = ensure_work_dir(work_dir)
    annotations = list(iter_jsonl(work_dir / "annotations.jsonl"))
    summaries = list(iter_jsonl(work_dir / "period-summaries.jsonl"))
    annotated_ids = {record["chunk_id"] for record in annotations}
    task_ids = {record["chunk_id"] for record in iter_jsonl(work_dir / "tasks.jsonl")}
    state = {
        "task_count": len(task_ids),
        "annotated_task_count": len(annotated_ids & task_ids),
        "pending_task_count": len(task_ids - annotated_ids),
        "period_summary_count": len(summaries),
        "overall_ready": (work_dir / "overall.json").is_file(),
        "target": manifest["target"],
    }
    write_json(work_dir / "state.json", state)


def prepare(input_path: Path, target: str, work_dir: Path) -> dict[str, Any]:
    input_path = input_path.resolve()
    work_dir = work_dir.resolve()
    if not input_path.is_file():
        raise ExtractorError(f"找不到聊天文件：{input_path}")
    target = target.strip()
    if not target:
        raise ExtractorError("target 不能为空")
    input_hash = sha256_file(input_path)

    if work_dir.exists():
        manifest = ensure_work_dir(work_dir)
        if manifest.get("input_sha256") == input_hash and manifest.get("target") == target:
            return manifest
        raise ExtractorError("工作目录已属于其他输入或目标人物，请换一个目录")

    work_dir.mkdir(parents=True)
    (work_dir / SENTINEL).write_text("chat-material-extractor\n", encoding="utf-8")
    try:
        normalized = normalize_messages(input_path, work_dir, target)
        stats, chunk_count, task_count = analyze_messages(work_dir, target, normalized)
        manifest = create_manifest(
            input_path, input_hash, work_dir, target, normalized, stats, chunk_count, task_count
        )
        write_json(work_dir / "manifest.json", manifest)
        update_state(work_dir)
        return manifest
    except Exception:
        if (work_dir / SENTINEL).is_file():
            shutil.rmtree(work_dir)
        raise


def load_tasks(work_dir: Path) -> list[dict[str, Any]]:
    ensure_work_dir(work_dir)
    return list(iter_jsonl(work_dir / "tasks.jsonl"))


def load_annotations(work_dir: Path) -> list[dict[str, Any]]:
    ensure_work_dir(work_dir)
    return list(iter_jsonl(work_dir / "annotations.jsonl"))


def load_materials(work_dir: Path) -> list[dict[str, Any]]:
    materials: list[dict[str, Any]] = []
    for envelope in load_annotations(work_dir):
        materials.extend(envelope.get("materials", []))
    return materials


def write_or_print(value: Any, output: Path | None) -> None:
    rendered = json_text(value, pretty=True) + "\n"
    if output:
        atomic_write_text(output, rendered)
    else:
        print(rendered, end="")


def next_tasks(work_dir: Path, limit: int) -> list[dict[str, Any]]:
    if limit < 1 or limit > 8:
        raise ExtractorError("limit 必须在 1～8 之间")
    done = {record["chunk_id"] for record in load_annotations(work_dir)}
    result = []
    manifest = ensure_work_dir(work_dir)
    for task in load_tasks(work_dir):
        if task["chunk_id"] in done:
            continue
        result.append(
            {
                "chunk_id": task["chunk_id"],
                "period": task["period"],
                "target": manifest["target"],
                "start_time": task["start_time"],
                "end_time": task["end_time"],
                "selection_reason": task["selection_reason"],
                "messages": [
                    {key: message[key] for key in ("id", "time", "sender", "text")}
                    for message in task["messages"]
                ],
            }
        )
        if len(result) == limit:
            break
    return result


def require_string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ExtractorError(f"{field} 必须是字符串")
    value = value.strip()
    if not value and not allow_empty:
        raise ExtractorError(f"{field} 不能为空")
    return value


def validate_material(
    raw: Any,
    task: dict[str, Any],
    index: int,
    target: str,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ExtractorError("Material 必须是 JSON 对象")
    material_type = require_string(raw.get("type"), "type")
    if material_type not in MATERIAL_TYPES:
        raise ExtractorError(f"不支持的 Material 类型：{material_type}")
    observation = require_string(raw.get("observation"), "observation")
    context = require_string(raw.get("context", ""), "context", allow_empty=True)
    tags = raw.get("tags", [])
    if not isinstance(tags, list) or len(tags) > 6 or any(not isinstance(tag, str) or not tag.strip() for tag in tags):
        raise ExtractorError("tags 必须是最多 6 个非空字符串")
    message_ids = raw.get("message_ids")
    if (
        not isinstance(message_ids, list)
        or not 1 <= len(message_ids) <= 6
        or any(not isinstance(message_id, str) for message_id in message_ids)
    ):
        raise ExtractorError("message_ids 必须包含 1～6 个字符串")
    message_ids = list(dict.fromkeys(message_ids))
    message_lookup = {message["id"]: message for message in task["messages"]}
    missing = [message_id for message_id in message_ids if message_id not in message_lookup]
    if missing:
        raise ExtractorError(f"{task['chunk_id']} 引用了不在本 Chunk 的消息：{missing}")
    if not any(message_lookup[message_id]["sender"] == target for message_id in message_ids):
        raise ExtractorError(f"{task['chunk_id']} 的 Material 至少要引用一条目标人物消息")
    evidence = [message_lookup[message_id] for message_id in message_ids]
    evidence.sort(key=lambda message: (message["_ts"], message["source_index"]))
    chunk_number = task["chunk_id"].removeprefix("chunk_")
    return {
        "material_id": f"mat_{chunk_number}_{index:02d}",
        "chunk_id": task["chunk_id"],
        "period": task["period"],
        "type": material_type,
        "target": target,
        "start_time": evidence[0]["time"],
        "end_time": evidence[-1]["time"],
        "start_ts": evidence[0]["_ts"],
        "end_ts": evidence[-1]["_ts"],
        "observation": observation,
        "context": context,
        "tags": list(dict.fromkeys(tag.strip() for tag in tags)),
        "message_ids": message_ids,
    }


def record_annotations(work_dir: Path, input_path: Path) -> int:
    manifest = ensure_work_dir(work_dir)
    payload = load_json(input_path)
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list) or not payload:
        raise ExtractorError("标注文件必须是非空 JSON 数组或对象")

    tasks = {task["chunk_id"]: task for task in load_tasks(work_dir)}
    existing = load_annotations(work_dir)
    completed = {record["chunk_id"] for record in existing}
    seen: set[str] = set()
    additions: list[dict[str, Any]] = []
    for envelope in payload:
        if not isinstance(envelope, dict):
            raise ExtractorError("每个标注 envelope 必须是 JSON 对象")
        chunk_id = require_string(envelope.get("chunk_id"), "chunk_id")
        if chunk_id in seen or chunk_id in completed:
            raise ExtractorError(f"{chunk_id} 已经记录")
        if chunk_id not in tasks:
            raise ExtractorError(f"未知 Chunk：{chunk_id}")
        seen.add(chunk_id)
        raw_materials = envelope.get("materials")
        if not isinstance(raw_materials, list) or len(raw_materials) > 3:
            raise ExtractorError("materials 必须是含 0～3 项的数组")
        materials = [
            validate_material(raw, tasks[chunk_id], index, manifest["target"])
            for index, raw in enumerate(raw_materials, 1)
        ]
        additions.append(
            {
                "chunk_id": chunk_id,
                "period": tasks[chunk_id]["period"],
                "materials": materials,
            }
        )

    task_order = {task_id: index for index, task_id in enumerate(tasks)}
    merged = sorted(existing + additions, key=lambda value: task_order[value["chunk_id"]])
    write_jsonl_atomic(work_dir / "annotations.jsonl", merged)
    update_state(work_dir)
    return len(additions)


def search_chunks(
    work_dir: Path,
    query: str,
    limit: int,
    after: str | None,
    before: str | None,
) -> list[dict[str, Any]]:
    manifest = ensure_work_dir(work_dir)
    if limit < 1 or limit > 100:
        raise ExtractorError("limit 必须在 1～100 之间")
    raw_terms = [term for term in re.split(r"[\s,，;；]+", query.strip()) if term]
    if not raw_terms:
        raise ExtractorError("query 不能为空")
    terms: list[str] = []
    for term in raw_terms:
        terms.extend(QUERY_EXPANSIONS.get(term, (term,)))
    terms = list(dict.fromkeys(terms))
    after_stamp = parse_time(after, where="after")[1] if after else None
    before_stamp = parse_time(before, where="before")[1] if before else None
    existing_ids = {task["chunk_id"] for task in load_tasks(work_dir)}
    candidates: list[tuple[float, float, dict[str, Any]]] = []

    for chunk in iter_jsonl(work_dir / "chunks.jsonl"):
        if chunk["chunk_id"] in existing_ids or not chunk["target_message_count"]:
            continue
        if after_stamp is not None and chunk["end_ts"] < after_stamp:
            continue
        if before_stamp is not None and chunk["start_ts"] > before_stamp:
            continue
        target_text = "\n".join(
            message["text"] for message in chunk["messages"] if message["sender"] == manifest["target"]
        )
        context_text = "\n".join(message["text"] for message in chunk["messages"])
        target_hits = sum(target_text.count(term) for term in terms)
        context_hits = sum(context_text.count(term) for term in terms)
        if not context_hits:
            continue
        score = target_hits * 3 + context_hits + chunk["score"] * 0.05
        candidates.append((score, chunk["start_ts"], chunk))

    selected = [
        item[2]
        for item in sorted(candidates, key=lambda item: (-item[0], item[1], item[2]["chunk_id"]))[:limit]
    ]
    if not selected:
        return []

    tasks = load_tasks(work_dir)
    additions = []
    for chunk in selected:
        chunk["selection_reason"] = f"targeted:{query.strip()}"
        additions.append(chunk)
    all_tasks = sorted(tasks + additions, key=lambda task: (task["start_ts"], task["chunk_id"]))
    write_jsonl_atomic(work_dir / "tasks.jsonl", all_tasks)

    stats = load_json(work_dir / "statistics.json")
    added_by_period = Counter(chunk["period"] for chunk in additions)
    for period in stats["periods"]:
        period["selected_chunks"] += added_by_period[period["period"]]
        period["selection_ratio"] = round(
            period["selected_chunks"] / period["candidate_chunks"], 4
        ) if period["candidate_chunks"] else 0
    write_json(work_dir / "statistics.json", stats)
    manifest["task_count"] = len(all_tasks)
    write_json(work_dir / "manifest.json", manifest)
    update_state(work_dir)
    return [
        {
            "chunk_id": chunk["chunk_id"],
            "period": chunk["period"],
            "start_time": chunk["start_time"],
            "end_time": chunk["end_time"],
            "matched_terms": [term for term in terms if term in "\n".join(m["text"] for m in chunk["messages"])],
        }
        for chunk in additions
    ]


def material_payload(material: dict[str, Any]) -> dict[str, Any]:
    return {
        key: material[key]
        for key in (
            "material_id", "chunk_id", "period", "type", "start_time", "end_time",
            "observation", "context", "tags",
        )
    }


def load_period_summaries(work_dir: Path) -> list[dict[str, Any]]:
    ensure_work_dir(work_dir)
    return list(iter_jsonl(work_dir / "period-summaries.jsonl"))


def pending_task_ids(work_dir: Path) -> set[str]:
    task_ids = {task["chunk_id"] for task in load_tasks(work_dir)}
    done = {annotation["chunk_id"] for annotation in load_annotations(work_dir)}
    return task_ids - done


def next_period_summary(work_dir: Path) -> list[dict[str, Any]]:
    pending = pending_task_ids(work_dir)
    if pending:
        raise ExtractorError(f"仍有 {len(pending)} 个 Chunk 未标注")
    manifest = ensure_work_dir(work_dir)
    materials_by_period: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for material in load_materials(work_dir):
        materials_by_period[material["period"]].append(material)
    existing = {summary["period"]: summary for summary in load_period_summaries(work_dir)}
    stats = load_json(work_dir / "statistics.json")
    labels = {period["period"]: period["label"] for period in stats["periods"]}
    for period in labels:
        materials = sorted(materials_by_period.get(period, []), key=lambda item: (item["start_ts"], item["material_id"]))
        if not materials:
            continue
        source_ids = [material["material_id"] for material in materials]
        if existing.get(period, {}).get("source_material_ids") == source_ids:
            continue
        return [
            {
                "period": period,
                "period_label": labels[period],
                "target": manifest["target"],
                "materials": [material_payload(material) for material in materials],
            }
        ]
    return []


def validate_pattern(
    raw: Any,
    available_ids: set[str],
    field: str,
    *,
    minimum_evidence: int = 2,
) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ExtractorError(f"{field} 必须是 JSON 对象")
    dimension = require_string(raw.get("dimension"), f"{field}.dimension")
    if any(mark in dimension for mark in ("*", "_", "`", "#")):
        raise ExtractorError(f"{field}.dimension 只能是纯文本，不要添加 Markdown 标记")
    summary = require_string(raw.get("summary"), f"{field}.summary")
    conditions = require_string(raw.get("conditions", ""), f"{field}.conditions", allow_empty=True)
    material_ids = raw.get("material_ids")
    if (
        not isinstance(material_ids, list)
        or any(not isinstance(item, str) for item in material_ids)
        or len(set(material_ids)) < minimum_evidence
    ):
        raise ExtractorError(f"{field}.material_ids 至少需要 {minimum_evidence} 个不同 Material ID")
    material_ids = list(dict.fromkeys(material_ids))
    missing = set(material_ids) - available_ids
    if missing:
        raise ExtractorError(f"{field} 引用了未知 Material：{sorted(missing)}")
    counter_ids = raw.get("counterexample_ids", [])
    if not isinstance(counter_ids, list) or any(not isinstance(item, str) for item in counter_ids):
        raise ExtractorError(f"{field}.counterexample_ids 必须是字符串数组")
    counter_ids = list(dict.fromkeys(counter_ids))
    missing = set(counter_ids) - available_ids
    if missing:
        raise ExtractorError(f"{field} 引用了未知反例：{sorted(missing)}")
    return {
        "dimension": dimension,
        "summary": summary,
        "conditions": conditions,
        "material_ids": material_ids,
        "counterexample_ids": counter_ids,
    }


def record_period_summary(work_dir: Path, input_path: Path) -> str:
    payload = load_json(input_path)
    if isinstance(payload, list):
        if len(payload) != 1:
            raise ExtractorError("分期概括文件必须只包含一个时期")
        payload = payload[0]
    if not isinstance(payload, dict):
        raise ExtractorError("分期概括必须是 JSON 对象")
    period = require_string(payload.get("period"), "period")
    summary_text = require_string(payload.get("summary"), "summary")
    current_materials = [material for material in load_materials(work_dir) if material["period"] == period]
    if not current_materials:
        raise ExtractorError(f"{period} 没有可概括的 Material")
    material_lookup = {material["material_id"]: material for material in current_materials}
    available_ids = set(material_lookup)
    raw_patterns = payload.get("patterns", [])
    if not isinstance(raw_patterns, list) or len(raw_patterns) > 8:
        raise ExtractorError("patterns 必须是最多 8 项的数组")
    patterns = [
        validate_pattern(raw, available_ids, f"patterns[{index}]")
        for index, raw in enumerate(raw_patterns)
    ]
    for index, pattern in enumerate(patterns):
        field = f"patterns[{index}]"
        if pattern["dimension"] in GENERIC_DIMENSIONS:
            raise ExtractorError(f"{field}.dimension 过于笼统，请写成“具体场景/主题 + 可观察做法”")
        if len(re.sub(r"\s+", "", pattern["summary"])) < 24:
            raise ExtractorError(f"{field}.summary 过短，需写明具体场景与可观察做法")
        if len(re.sub(r"\s+", "", pattern["conditions"])) < 10:
            raise ExtractorError(f"{field}.conditions 过短，需写明具体适用情境与证据边界")
        chunks = {material_lookup[item]["chunk_id"] for item in pattern["material_ids"]}
        if len(chunks) < 2:
            raise ExtractorError(f"{field} 的重复模式至少需要两个不同 Chunk 的证据")
    record = {
        "period": period,
        "summary": summary_text,
        "patterns": patterns,
        "source_material_ids": [
            material["material_id"]
            for material in sorted(current_materials, key=lambda item: (item["start_ts"], item["material_id"]))
        ],
    }
    summaries = {item["period"]: item for item in load_period_summaries(work_dir)}
    summaries[period] = record
    period_order = {
        item["period"]: index
        for index, item in enumerate(load_json(work_dir / "statistics.json")["periods"])
    }
    ordered = sorted(summaries.values(), key=lambda item: period_order.get(item["period"], 10**9))
    write_jsonl_atomic(work_dir / "period-summaries.jsonl", ordered)
    update_state(work_dir)
    return period


def valid_period_summaries(work_dir: Path) -> list[dict[str, Any]]:
    current_ids: dict[str, list[str]] = defaultdict(list)
    for material in sorted(load_materials(work_dir), key=lambda item: (item["start_ts"], item["material_id"])):
        current_ids[material["period"]].append(material["material_id"])
    return [
        summary
        for summary in load_period_summaries(work_dir)
        if summary.get("source_material_ids") == current_ids.get(summary["period"], [])
    ]


def summary_signature(summaries: list[dict[str, Any]]) -> str:
    canonical = json.dumps(summaries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def overall_input(work_dir: Path) -> dict[str, Any]:
    pending = next_period_summary(work_dir)
    if pending:
        raise ExtractorError(f"时期 {pending[0]['period']} 尚未概括")
    manifest = ensure_work_dir(work_dir)
    summaries = valid_period_summaries(work_dir)
    return {
        "target": manifest["target"],
        "period_summaries": [
            {
                "period": item["period"],
                "summary": item["summary"],
                "patterns": item["patterns"],
                "source_material_ids": item["source_material_ids"],
            }
            for item in summaries
        ],
    }


def validate_overall_pattern(
    raw: Any,
    material_lookup: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, Any]:
    pattern = validate_pattern(raw, set(material_lookup), field)
    periods = {material_lookup[item]["period"] for item in pattern["material_ids"]}
    if len(periods) < 2:
        raise ExtractorError(f"{field} 必须由至少两个时期支持")
    return pattern


def record_overall(work_dir: Path, input_path: Path) -> None:
    payload = load_json(input_path)
    if not isinstance(payload, dict):
        raise ExtractorError("综合概括必须是 JSON 对象")
    summary_text = require_string(payload.get("summary"), "summary")
    materials = load_materials(work_dir)
    material_lookup = {material["material_id"]: material for material in materials}
    recurring_raw = payload.get("recurring_patterns", [])
    variations_raw = payload.get("time_variations", [])
    uncertainties = payload.get("uncertainties", [])
    if not isinstance(recurring_raw, list) or len(recurring_raw) > 12:
        raise ExtractorError("recurring_patterns 必须是最多 12 项的数组")
    if not isinstance(variations_raw, list) or len(variations_raw) > 12:
        raise ExtractorError("time_variations 必须是最多 12 项的数组")
    if (
        not isinstance(uncertainties, list)
        or len(uncertainties) > 12
        or any(not isinstance(item, str) or not item.strip() for item in uncertainties)
    ):
        raise ExtractorError("uncertainties 必须是最多 12 个非空字符串")

    recurring = [
        validate_overall_pattern(raw, material_lookup, f"recurring_patterns[{index}]")
        for index, raw in enumerate(recurring_raw)
    ]
    period_order = {
        item["period"]: index
        for index, item in enumerate(load_json(work_dir / "statistics.json")["periods"])
    }
    variations = []
    for index, raw in enumerate(variations_raw):
        field = f"time_variations[{index}]"
        if not isinstance(raw, dict):
            raise ExtractorError(f"{field} 必须是 JSON 对象")
        dimension = require_string(raw.get("dimension"), f"{field}.dimension")
        summary = require_string(raw.get("summary"), f"{field}.summary")
        earlier = raw.get("earlier_material_ids")
        later = raw.get("later_material_ids")
        if (
            not isinstance(earlier, list) or not earlier
            or not isinstance(later, list) or not later
            or any(not isinstance(item, str) for item in earlier + later)
        ):
            raise ExtractorError(f"{field} 必须同时提供较早和较晚 Material ID")
        earlier = list(dict.fromkeys(earlier))
        later = list(dict.fromkeys(later))
        missing = (set(earlier) | set(later)) - set(material_lookup)
        if missing:
            raise ExtractorError(f"{field} 引用了未知 Material：{sorted(missing)}")
        earlier_positions = {period_order[material_lookup[item]["period"]] for item in earlier}
        later_positions = {period_order[material_lookup[item]["period"]] for item in later}
        if max(earlier_positions) >= min(later_positions):
            raise ExtractorError(f"{field} 的 earlier_material_ids 必须早于 later_material_ids")
        variations.append(
            {
                "dimension": dimension,
                "summary": summary,
                "earlier_material_ids": earlier,
                "later_material_ids": later,
            }
        )

    summaries = valid_period_summaries(work_dir)
    overall = {
        "summary": summary_text,
        "recurring_patterns": recurring,
        "time_variations": variations,
        "uncertainties": [item.strip() for item in uncertainties],
        "source_summary_signature": summary_signature(summaries),
    }
    write_json(work_dir / "overall.json", overall)
    update_state(work_dir)


def current_overall(work_dir: Path) -> dict[str, Any]:
    path = work_dir / "overall.json"
    if not path.is_file():
        raise ExtractorError("尚未记录综合概括")
    overall = load_json(path)
    if overall.get("source_summary_signature") != summary_signature(valid_period_summaries(work_dir)):
        raise ExtractorError("综合概括已过期，请基于最新分期概括重新生成")
    return overall


def md_inline(value: Any) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ↩ ").strip()
    return html.escape(text, quote=False).replace("|", "&#124;")


def format_seconds(value: Any) -> str:
    if value is None:
        return "无可用样本"
    seconds = float(value)
    if seconds < 60:
        return f"{seconds:.0f} 秒"
    if seconds < 3600:
        return f"{seconds / 60:.1f} 分钟"
    return f"{seconds / 3600:.1f} 小时"


def material_links(ids: list[str], lookup: dict[str, dict[str, Any]]) -> str:
    return "、".join(f"{lookup[item]['period']} / {item}" for item in ids)


def render_report(work_dir: Path) -> str:
    pending = pending_task_ids(work_dir)
    if pending:
        raise ExtractorError(f"仍有 {len(pending)} 个 Chunk 未标注")
    if next_period_summary(work_dir):
        raise ExtractorError("仍有时期未完成抽象概括")
    manifest = ensure_work_dir(work_dir)
    stats = load_json(work_dir / "statistics.json")
    overall = current_overall(work_dir)
    summaries = {item["period"]: item for item in valid_period_summaries(work_dir)}
    materials = sorted(load_materials(work_dir), key=lambda item: (item["start_ts"], item["material_id"]))
    material_lookup = {material["material_id"]: material for material in materials}
    task_lookup = {task["chunk_id"]: task for task in load_tasks(work_dir)}
    evidence_lookup: dict[str, dict[str, Any]] = {}
    for task in task_lookup.values():
        for message in task["messages"]:
            evidence_lookup[message["id"]] = message

    lines = [
        f"# 聊天人物素材报告：{md_inline(manifest['target'])}",
        "",
        "> 本报告对多个聊天片段进行证据约束的分期归纳，供后续人物分析使用；不是心理诊断或最终人格结论。",
        "",
        "## 1. 综合概括",
        "",
        md_inline(overall["summary"]),
        "",
        "### 跨期反复出现的表现",
        "",
    ]
    if overall["recurring_patterns"]:
        for pattern in overall["recurring_patterns"]:
            lines.extend(
                [
                    f"- **{md_inline(pattern['dimension'])}**：{md_inline(pattern['summary'])}",
                    f"  - 适用情境：{md_inline(pattern['conditions']) or '未限定'}",
                    f"  - 证据：{md_inline(material_links(pattern['material_ids'], material_lookup))}",
                ]
            )
            if pattern["counterexample_ids"]:
                lines.append(
                    f"  - 反例或边界：{md_inline(material_links(pattern['counterexample_ids'], material_lookup))}"
                )
    else:
        lines.append("- 当前素材不足以确认跨期反复模式。")

    lines.extend(["", "### 前后时期的表现差异", ""])
    if overall["time_variations"]:
        for variation in overall["time_variations"]:
            lines.extend(
                [
                    f"- **{md_inline(variation['dimension'])}**：{md_inline(variation['summary'])}",
                    f"  - 较早证据：{md_inline(material_links(variation['earlier_material_ids'], material_lookup))}",
                    f"  - 较晚证据：{md_inline(material_links(variation['later_material_ids'], material_lookup))}",
                ]
            )
    else:
        lines.append("- 当前素材不足以确认清晰的跨期差异。")

    lines.extend(["", "### 尚不能确定", ""])
    if overall["uncertainties"]:
        lines.extend(f"- {md_inline(item)}" for item in overall["uncertainties"])
    else:
        lines.append("- 无额外项；仍须遵守文末的抽样与解释边界。")

    lines.extend(["", "## 2. 分期概括", ""])
    materials_by_period: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for material in materials:
        materials_by_period[material["period"]].append(material)
    for period_info in stats["periods"]:
        period = period_info["period"]
        lines.extend([f"### {md_inline(period_info['label'])}", ""])
        summary = summaries.get(period)
        if not summary:
            lines.append("本期入选片段未形成足够的可概括素材。")
            lines.append("")
            continue
        lines.extend([md_inline(summary["summary"]), ""])
        if summary["patterns"]:
            for pattern in summary["patterns"]:
                lines.extend(
                    [
                        f"- **{md_inline(pattern['dimension'])}**：{md_inline(pattern['summary'])}",
                        f"  - 适用情境：{md_inline(pattern['conditions']) or '未限定'}",
                        f"  - 证据：{md_inline('、'.join(pattern['material_ids']))}",
                    ]
                )
                if pattern["counterexample_ids"]:
                    lines.append(f"  - 反例或边界：{md_inline('、'.join(pattern['counterexample_ids']))}")
        else:
            lines.append("- 本期素材数量不足以形成重复模式，仅保留下方单点观察。")
        lines.append("")

    lines.extend(
        [
            "## 3. 覆盖情况",
            "",
            f"- 数据文件：{md_inline(manifest['input_name'])}",
            f"- 目标人物：{md_inline(manifest['target'])}",
            f"- 聊天对象：{md_inline('、'.join(name for name in manifest['participants'] if name != manifest['target']) or '未识别')}",
            f"- 时间范围：{md_inline(manifest['start_time'])} 至 {md_inline(manifest['end_time'])}",
            f"- 原始记录：{manifest['raw_record_count']} 条",
            f"- 有效文字消息：{manifest['valid_text_message_count']} 条",
            f"- 跳过的非文字或空记录：{manifest['skipped_record_count']} 条",
            f"- Session：{stats['session_count']} 个；Chunk：{manifest['chunk_count']} 个；已分析 Chunk：{manifest['task_count']} 个",
            "",
            "| 时期 | 全部消息 | 目标人物消息 | 候选 Chunk | 已分析 Chunk | 覆盖率 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in stats["periods"]:
        lines.append(
            f"| {md_inline(item['label'])} | {item['message_count']} | {item['target_message_count']} | "
            f"{item['candidate_chunks']} | {item['selected_chunks']} | {item['selection_ratio']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## 4. 客观概览",
            "",
            "| 人物 | 消息数 | 平均长度 | 中位长度 | 短消息比例 | 发起 Session | 回复中位时间 | 平均连续发送 |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for sender, count in stats["participants"].items():
        initiation = stats["session_initiation"][sender]
        lines.append(
            f"| {md_inline(sender)} | {count} | {stats['avg_message_length'][sender]} | "
            f"{stats['median_message_length'][sender]} | {stats['short_message_ratio'][sender]:.1%} | "
            f"{initiation['count']}（{initiation['ratio']:.1%}） | "
            f"{format_seconds(stats['median_reply_seconds'][sender])} | "
            f"{stats['avg_consecutive_messages'][sender] or '无'} |"
        )

    lines.extend(["", "### 活跃时段、高频表达与标点", ""])
    for sender in stats["participants"]:
        hours = sorted(
            ((int(hour), count) for hour, count in stats["active_hours"][sender].items()),
            key=lambda item: (-item[1], item[0]),
        )[:5]
        hour_text = "、".join(f"{hour:02d} 时（{count}）" for hour, count in hours if count) or "无"
        phrase_text = "、".join(
            f"“{md_inline(item['text'])}”（{item['count']}）"
            for item in stats["common_phrases"][sender]
        ) or "无"
        punctuation_text = "、".join(
            f"“{md_inline(mark)}”（{count}）"
            for mark, count in stats["punctuation"][sender].items()
        ) or "无"
        lines.extend(
            [
                f"- **{md_inline(sender)}**",
                f"  - 活跃小时：{hour_text}",
                f"  - 高频词/短语：{phrase_text}",
                f"  - 标点：{punctuation_text}",
            ]
        )

    lines.extend(["", "## 5. 分期证据附录", ""])
    if not materials:
        lines.append("没有提取到符合边界的 Material。")
    for period_info in stats["periods"]:
        period = period_info["period"]
        period_materials = materials_by_period.get(period, [])
        if not period_materials:
            continue
        lines.extend([f"### {md_inline(period_info['label'])}", ""])
        for material in period_materials:
            lines.extend(
                [
                    f"#### {material['material_id']} · {material['type']}",
                    "",
                    f"- 时间：{md_inline(material['start_time'])} 至 {md_inline(material['end_time'])}",
                    f"- 单点观察：{md_inline(material['observation'])}",
                    f"- 当时情境：{md_inline(material['context']) or '未补充'}",
                    f"- 标签：{md_inline('、'.join(material['tags']) or '无')}",
                    "- 原文证据：",
                ]
            )
            for message_id in material["message_ids"]:
                message = evidence_lookup[message_id]
                lines.append(
                    f"  > [{message_id} | {md_inline(message['time'])} | {md_inline(message['sender'])}] "
                    f"{md_inline(message['text'])}"
                )
            lines.append("")

    by_type: dict[str, list[str]] = defaultdict(list)
    by_tag: dict[str, list[str]] = defaultdict(list)
    for material in materials:
        by_type[material["type"]].append(material["material_id"])
        for tag in material["tags"]:
            by_tag[tag].append(material["material_id"])
    lines.extend(["## 6. 素材索引", "", "### 按类型", ""])
    if by_type:
        for material_type in sorted(by_type):
            lines.append(f"- {material_type}：{md_inline('、'.join(by_type[material_type]))}")
    else:
        lines.append("- 无")
    lines.extend(["", "### 按标签", ""])
    if by_tag:
        for tag in sorted(by_tag):
            lines.append(f"- {md_inline(tag)}：{md_inline('、'.join(by_tag[tag]))}")
    else:
        lines.append("- 无")

    lines.extend(
        [
            "",
            "## 7. 使用边界",
            "",
            f"- 抽样规则：{md_inline(stats['definitions']['sampling'])}，并可通过 V1.2 定向检索追加片段。",
            "- 抽象概括只建立在已分析 Chunk 和所引 Material 上；没有被抽中的聊天不代表没有相关表现。",
            "- 跨期反复项至少需要两个时期的证据；分期模式至少需要两个 Material。",
            "- 前后差异只描述观察到的表现，不证明性格发生变化，也不解释原因。",
            "- 本报告不能单独用于心理诊断、人格定型、动机判断或行为预测。",
            f"- 短消息定义：{md_inline(stats['definitions']['short_message'])}；分段：{md_inline(stats['definitions']['chunk'])}。",
            "",
        ]
    )
    return "\n".join(lines)


def safe_remove_work_dir(work_dir: Path, output: Path) -> None:
    work_dir = work_dir.resolve()
    output = output.resolve()
    if not (work_dir / SENTINEL).is_file():
        raise ExtractorError("拒绝清理没有本工具标记的目录")
    if output == work_dir or work_dir in output.parents:
        raise ExtractorError("输出文件不能位于即将清理的工作目录内")
    shutil.rmtree(work_dir)


def core_report_path(output: Path) -> Path:
    return output.with_name(f"{output.stem}_core{output.suffix or '.md'}")


def build_report(work_dir: Path, output: Path, *, keep_work: bool, force: bool) -> None:
    work_dir = work_dir.resolve()
    output = output.resolve()
    core_output = core_report_path(output)
    existing = [path for path in (output, core_output) if path.exists()]
    if existing and not force:
        raise ExtractorError(f"输出已存在：{existing[0]}；确认覆盖时使用 --force")
    if not keep_work and any(path == work_dir or work_dir in path.parents for path in (output, core_output)):
        raise ExtractorError("输出文件不能位于即将清理的工作目录内")
    report = render_report(work_dir)
    atomic_write_text(output, report)
    core = report.split("\n## 5. 分期证据附录", 1)[0].rstrip() + "\n"
    atomic_write_text(core_output, core)
    if not keep_work:
        safe_remove_work_dir(work_dir, output)


def load_env(path: Path | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if path and path.is_file():
        for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                raise ExtractorError(f"{path} 第 {line_number} 行不是 KEY=VALUE")
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    for key in ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_TIMEOUT_SECONDS", "LLM_MAX_RETRIES"):
        if key in os.environ:
            values[key] = os.environ[key]
    return values


def api_config(env_file: Path | None) -> dict[str, Any]:
    values = load_env(env_file)
    provider = values.get("LLM_PROVIDER", "openai-responses")
    if provider != "openai-responses":
        raise ExtractorError("当前仅支持 LLM_PROVIDER=openai-responses")
    key = values.get("LLM_API_KEY", "").strip()
    model = values.get("LLM_MODEL", "").strip()
    if not key or not model:
        raise ExtractorError("请在 .env 或环境变量中设置 LLM_API_KEY 和 LLM_MODEL")
    try:
        timeout = float(values.get("LLM_TIMEOUT_SECONDS", "120"))
        retries = int(values.get("LLM_MAX_RETRIES", "3"))
    except ValueError as exc:
        raise ExtractorError("LLM_TIMEOUT_SECONDS 或 LLM_MAX_RETRIES 格式无效") from exc
    if timeout <= 0 or not 1 <= retries <= 10:
        raise ExtractorError("超时必须大于 0，重试次数必须在 1～10 之间")
    base = values.get("LLM_BASE_URL", "").strip() or "https://api.openai.com/v1"
    endpoint = base.rstrip("/")
    if not endpoint.endswith("/responses"):
        endpoint += "/responses"
    return {"endpoint": endpoint, "key": key, "model": model, "timeout": timeout, "retries": retries}


def pattern_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["dimension", "summary", "conditions", "material_ids", "counterexample_ids"],
        "properties": {
            "dimension": {"type": "string"}, "summary": {"type": "string"},
            "conditions": {"type": "string"},
            "material_ids": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            "counterexample_ids": {"type": "array", "items": {"type": "string"}},
        },
    }


def response_schema(kind: str) -> dict[str, Any]:
    if kind == "chunk":
        material = {
            "type": "object", "additionalProperties": False,
            "required": ["type", "observation", "context", "tags", "message_ids"],
            "properties": {
                "type": {"type": "string", "enum": sorted(MATERIAL_TYPES)},
                "observation": {"type": "string"}, "context": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
                "message_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6},
            },
        }
        return {"type": "array", "minItems": 1, "maxItems": 1, "items": {
            "type": "object", "additionalProperties": False, "required": ["chunk_id", "materials"],
            "properties": {"chunk_id": {"type": "string"}, "materials": {"type": "array", "items": material, "maxItems": 3}},
        }}
    if kind == "period":
        return {"type": "object", "additionalProperties": False, "required": ["period", "summary", "patterns"],
                "properties": {"period": {"type": "string"}, "summary": {"type": "string"},
                               "patterns": {"type": "array", "items": pattern_schema(), "maxItems": 8}}}
    variation = {
        "type": "object", "additionalProperties": False,
        "required": ["dimension", "summary", "earlier_material_ids", "later_material_ids"],
        "properties": {"dimension": {"type": "string"}, "summary": {"type": "string"},
                       "earlier_material_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                       "later_material_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1}},
    }
    return {"type": "object", "additionalProperties": False,
            "required": ["summary", "recurring_patterns", "time_variations", "uncertainties"],
            "properties": {"summary": {"type": "string"},
                           "recurring_patterns": {"type": "array", "items": pattern_schema(), "maxItems": 12},
                           "time_variations": {"type": "array", "items": variation, "maxItems": 12},
                           "uncertainties": {"type": "array", "items": {"type": "string"}, "maxItems": 12}}}


def prompt_section(kind: str) -> str:
    text = (Path(__file__).resolve().parents[1] / "prompts" / "extract_material.md").read_text(encoding="utf-8")
    markers = {"chunk": ("## A.", "## B."), "period": ("## B.", "## C."), "overall": ("## C.", None)}
    start, end = markers[kind]
    section = text[text.index(start):]
    return section[:section.index(end)] if end else section


def response_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
            if content.get("type") == "refusal":
                raise ExtractorError(f"模型拒绝处理：{content.get('refusal', '')}")
    raise ExtractorError("Responses API 返回中没有 output_text")


def call_responses_api(config: dict[str, Any], kind: str, value: Any) -> Any:
    body = json.dumps({
        "model": config["model"], "instructions": prompt_section(kind),
        "input": json_text(value, pretty=True), "store": False,
        "text": {"format": {"type": "json_schema", "name": f"chat_material_{kind}",
                            "strict": True, "schema": response_schema(kind)}},
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(config["endpoint"], data=body, method="POST", headers={
        "Authorization": f"Bearer {config['key']}", "Content-Type": "application/json",
    })
    for attempt in range(config["retries"]):
        try:
            with urllib.request.urlopen(request, timeout=config["timeout"]) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if payload.get("error"):
                raise ExtractorError(f"Responses API 错误：{payload['error']}")
            return json.loads(response_text(payload))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            if attempt + 1 < config["retries"] and (exc.code in (408, 409, 429) or exc.code >= 500):
                time.sleep(2 ** attempt)
                continue
            raise ExtractorError(f"Responses API HTTP {exc.code}：{detail}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 < config["retries"]:
                time.sleep(2 ** attempt)
                continue
            raise ExtractorError(f"无法连接 Responses API：{exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise ExtractorError("Responses API 未返回有效 JSON") from exc
    raise ExtractorError("Responses API 请求失败")


def record_api_result(work_dir: Path, payload: Any, recorder: Any) -> Any:
    path = work_dir / ".api-result.json"
    write_json(path, payload)
    try:
        return recorder(work_dir, path)
    finally:
        path.unlink(missing_ok=True)


def run_pipeline(input_path: Path, target: str, output: Path, work_dir: Path, env_file: Path | None,
                 focus: str | None, keep_work: bool, force: bool) -> None:
    existing = [path for path in (output, core_report_path(output)) if path.exists()]
    if existing and not force:
        raise ExtractorError(f"输出已存在：{existing[0]}；确认覆盖时使用 --force")
    config = api_config(env_file)
    prepare(input_path, target, work_dir)
    focus_reason = f"targeted:{focus.strip()}" if focus else None
    if focus and not any(task.get("selection_reason") == focus_reason for task in load_tasks(work_dir)):
        search_chunks(work_dir, focus, 12, None, None)
    while tasks := next_tasks(work_dir, 1):
        print(f"分析 Chunk：{tasks[0]['chunk_id']}", file=sys.stderr)
        record_api_result(work_dir, call_responses_api(config, "chunk", tasks[0]), record_annotations)
    while periods := next_period_summary(work_dir):
        print(f"概括时期：{periods[0]['period']}", file=sys.stderr)
        record_api_result(work_dir, call_responses_api(config, "period", periods[0]), record_period_summary)
    print("生成跨期概括", file=sys.stderr)
    record_api_result(work_dir, call_responses_api(config, "overall", overall_input(work_dir)), record_overall)
    build_report(work_dir, output, keep_work=keep_work, force=force)


def self_test() -> None:
    assert json.loads(response_text({"output": [{"content": [{"type": "output_text", "text": "{\"ok\": true}"}]}]}))["ok"]
    assert response_schema("chunk")["maxItems"] == 1
    with tempfile.TemporaryDirectory(prefix="chat-material-extractor-") as root_text:
        root = Path(root_text)
        wrapped = root / "wrapped.json"
        write_json(wrapped, {"schema": "wechat-text-export-v1", "stats": {"messages": 1}, "messages": [
            {"time": "2023-01-01T00:00:00+08:00", "sender": "甲", "text": "包装格式"}
        ]})
        assert input_sender_counts(wrapped)["senders"] == {"甲": 1}
        source = root / "chat.json"
        work = root / "work"
        report = root / "report.md"
        sample = [
            {"time": "2023-01-01T10:00:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "甲", "text": "我现在很生气，先把问题说清楚。"},
            {"time": "2023-01-01T10:03:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "乙", "text": "好，你说。"},
            {"time": "2023-01-01T10:05:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "甲", "text": "我不喜欢你突然不回消息。"},
            {"time": "2023-01-01T11:05:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "乙", "text": "刚才在忙，对不起。"},
            {"time": "2023-01-01T11:06:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "甲", "text": "知道了。"},
            {"time": "2023-02-15T20:00:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "甲", "text": "我有点不舒服，想晚点再聊。"},
            {"time": "2023-02-15T20:02:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "乙", "text": "好，你休息好了告诉我。"},
            {"time": "2023-02-15T21:30:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "甲", "text": "现在可以聊了，我想慢慢说。"},
            {"time": "2023-02-15T21:31:00+08:00", "chat": "关系样例", "chat_id": "1", "sender": "乙", "text": "嗯，我在听。"},
        ]
        for index, hour in enumerate(range(8, 20, 2), 1):
            sample.extend(
                [
                    {
                        "time": f"2023-03-01T{hour:02d}:00:00+08:00",
                        "chat": "关系样例",
                        "chat_id": "1",
                        "sender": "甲",
                        "text": f"定向词{index}，这是普通记录。",
                    },
                    {
                        "time": f"2023-03-01T{hour:02d}:01:00+08:00",
                        "chat": "关系样例",
                        "chat_id": "1",
                        "sender": "乙",
                        "text": "收到。",
                    },
                ]
            )
        source.write_text(json_text(sample, pretty=True), encoding="utf-8")
        manifest = prepare(source, "甲", work)
        stats = load_json(work / "statistics.json")
        assert manifest["version"] == VERSION
        assert stats["session_count"] == 10
        assert [item["period"] for item in stats["periods"]] == ["2023-01", "2023-02", "2023-03"]
        assert all(item["selected_chunks"] == max(1, math.ceil(item["candidate_chunks"] * SAMPLE_RATIO)) for item in stats["periods"])

        initially_selected = {task["chunk_id"] for task in load_tasks(work)}
        unselected = next(
            chunk
            for chunk in iter_jsonl(work / "chunks.jsonl")
            if chunk["period"] == "2023-03" and chunk["chunk_id"] not in initially_selected
        )
        query = next(
            re.search(r"定向词\d+", message["text"]).group(0)
            for message in unselected["messages"]
            if message["sender"] == "甲" and re.search(r"定向词\d+", message["text"])
        )
        additions = search_chunks(work, query, 1, None, None)
        assert len(additions) == 1
        assert additions[0]["chunk_id"] == unselected["chunk_id"]

        annotations = []
        for task in load_tasks(work):
            target_messages = [message for message in task["messages"] if message["sender"] == "甲"]
            if not target_messages:
                materials = []
            elif task["period"] == "2023-01":
                materials = [
                    {
                        "type": "conflict",
                        "observation": "目标人物在不满出现时直接指出具体问题。",
                        "context": "双方讨论未及时回复消息。",
                        "tags": ["表达不满", "直接沟通"],
                        "message_ids": [message["id"] for message in target_messages[:2]],
                    }
                ]
            else:
                materials = [
                    {
                        "type": "interaction",
                        "observation": "目标人物先暂停交流，之后主动恢复讨论。",
                        "context": "目标人物表示身体不适。",
                        "tags": ["暂缓沟通", "恢复交流"],
                        "message_ids": [message["id"] for message in target_messages[:2]],
                    }
                ]
            if materials:
                second = dict(materials[0])
                second["type"] = "language"
                second["observation"] = "目标人物用较短的陈述说明当下处理方式。"
                second["tags"] = ["表达方式", task["period"]]
                materials.append(second)
            annotations.append({"chunk_id": task["chunk_id"], "materials": materials})
        annotation_path = root / "annotations.json"
        write_json(annotation_path, annotations)
        record_annotations(work, annotation_path)
        assert not pending_task_ids(work)

        while True:
            pending_summary = next_period_summary(work)
            if not pending_summary:
                break
            item = pending_summary[0]
            material_ids = [material["material_id"] for material in item["materials"]]
            pattern_ids = list({material["chunk_id"]: material["material_id"] for material in item["materials"]}.values())[:2]
            summary_payload = {
                "period": item["period"],
                "summary": "本期材料呈现一种有明确时间边界的沟通表现。",
                "patterns": [
                    {
                        "dimension": "具体任务中的状态说明",
                        "summary": "在学习安排和日常任务等不同片段中，目标人物会明确说明当下状态并交代接下来的处理方式。",
                        "conditions": "仅限本期已抽样的文字聊天。",
                        "material_ids": pattern_ids,
                        "counterexample_ids": [],
                    }
                ] if len(pattern_ids) >= 2 else [],
            }
            summary_path = root / "period-summary.json"
            write_json(summary_path, summary_payload)
            record_period_summary(work, summary_path)

        materials = load_materials(work)
        earlier = [item["material_id"] for item in materials if item["period"] == "2023-01"]
        later = [item["material_id"] for item in materials if item["period"] == "2023-02"]
        overall_path = root / "overall-input-result.json"
        write_json(
            overall_path,
            {
                "summary": "两个时期呈现不同的沟通处理方式，证据仅限样例片段。",
                "recurring_patterns": [
                    {
                        "dimension": "说明当下状态",
                        "summary": "不同月份都出现目标人物说明当下状态或处理方式的情况。",
                        "conditions": "只覆盖样例中的分歧与不适场景。",
                        "material_ids": [earlier[0], later[0]],
                        "counterexample_ids": [],
                    }
                ],
                "time_variations": [
                    {
                        "dimension": "不适情境下的沟通处理",
                        "summary": "较早时期直接指出问题，较晚时期先暂停再恢复沟通。",
                        "earlier_material_ids": earlier,
                        "later_material_ids": later,
                    }
                ],
                "uncertainties": ["样例量很小，不能判断这些表现是否稳定。"],
            },
        )
        record_overall(work, overall_path)
        build_report(work, report, keep_work=True, force=False)
        rendered = report.read_text(encoding="utf-8")
        core_rendered = core_report_path(report).read_text(encoding="utf-8")
        assert "## 1. 综合概括" in rendered
        assert "不同月份都出现" in rendered
        assert "较早时期直接指出问题" in rendered
        assert rendered.index("2023-01") < rendered.index("2023-02")
        assert "## 4. 客观概览" in core_rendered
        assert "## 5. 分期证据附录" not in core_rendered
        assert "## 6. 素材索引" not in core_rendered
        for material in materials:
            assert material["material_id"] in rendered
            assert all(message_id in rendered for message_id in material["message_ids"])
        print("self-test passed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Chat Material Extractor V1.2：生成有时间与证据约束的聊天人物素材报告。"
    )
    parser.add_argument("--version", action="version", version=VERSION)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="使用 Responses API 一次完成分析并生成 Markdown")
    run_parser.add_argument("input", type=Path)
    run_parser.add_argument("--target", required=True)
    run_parser.add_argument("--output", required=True, type=Path)
    run_parser.add_argument("--work-dir", type=Path)
    run_parser.add_argument("--env-file", type=Path, default=Path(".env"))
    run_parser.add_argument("--focus")
    run_parser.add_argument("--keep-work", action="store_true")
    run_parser.add_argument("--force", action="store_true")

    inspect_parser = subparsers.add_parser("inspect", help="列出有效文字消息中的 sender")
    inspect_parser.add_argument("input", type=Path)

    prepare_parser = subparsers.add_parser("prepare", help="标准化、统计、分段并选择 Chunk")
    prepare_parser.add_argument("input", type=Path)
    prepare_parser.add_argument("--target", required=True)
    prepare_parser.add_argument("--work-dir", required=True, type=Path)

    next_parser = subparsers.add_parser("next", help="输出下一批待标注 Chunk")
    next_parser.add_argument("--work-dir", required=True, type=Path)
    next_parser.add_argument("--limit", type=int, default=1)
    next_parser.add_argument("--output", type=Path)

    record_parser = subparsers.add_parser("record", help="校验并记录 Chunk 标注")
    record_parser.add_argument("--work-dir", required=True, type=Path)
    record_parser.add_argument("input", type=Path)

    search_parser = subparsers.add_parser("search", help="V1.2 定向检索并追加待分析 Chunk")
    search_parser.add_argument("--work-dir", required=True, type=Path)
    search_parser.add_argument("--query", required=True)
    search_parser.add_argument("--limit", type=int, default=12)
    search_parser.add_argument("--after")
    search_parser.add_argument("--before")

    summary_next_parser = subparsers.add_parser("summary-next", help="输出下一期待抽象 Material")
    summary_next_parser.add_argument("--work-dir", required=True, type=Path)
    summary_next_parser.add_argument("--output", type=Path)

    summary_record_parser = subparsers.add_parser("record-summary", help="校验并记录一期抽象概括")
    summary_record_parser.add_argument("--work-dir", required=True, type=Path)
    summary_record_parser.add_argument("input", type=Path)

    overall_input_parser = subparsers.add_parser("overall-input", help="输出跨期综合概括输入")
    overall_input_parser.add_argument("--work-dir", required=True, type=Path)
    overall_input_parser.add_argument("--output", type=Path)

    overall_record_parser = subparsers.add_parser("record-overall", help="校验并记录跨期综合概括")
    overall_record_parser.add_argument("--work-dir", required=True, type=Path)
    overall_record_parser.add_argument("input", type=Path)

    build_command = subparsers.add_parser("build", help="生成最终 Markdown")
    build_command.add_argument("--work-dir", required=True, type=Path)
    build_command.add_argument("--output", required=True, type=Path)
    build_command.add_argument("--keep-work", action="store_true")
    build_command.add_argument("--force", action="store_true")

    subparsers.add_parser("self-test", help="运行最小端到端自检")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "run":
            output = args.output.resolve()
            work_dir = args.work_dir.resolve() if args.work_dir else output.with_name(f".{output.stem}.work")
            run_pipeline(args.input.resolve(), args.target, output, work_dir,
                         args.env_file.resolve() if args.env_file else None,
                         args.focus, args.keep_work, args.force)
            write_or_print({"full_report": str(output), "core_report": str(core_report_path(output))}, None)
        elif args.command == "inspect":
            write_or_print(input_sender_counts(args.input.resolve()), None)
        elif args.command == "prepare":
            manifest = prepare(args.input, args.target, args.work_dir)
            write_or_print(
                {
                    "version": manifest["version"],
                    "target": manifest["target"],
                    "messages": manifest["valid_text_message_count"],
                    "chunks": manifest["chunk_count"],
                    "selected_chunks": manifest["task_count"],
                    "work_dir": manifest["work_dir"],
                },
                None,
            )
        elif args.command == "next":
            write_or_print(next_tasks(args.work_dir.resolve(), args.limit), args.output)
        elif args.command == "record":
            count = record_annotations(args.work_dir.resolve(), args.input.resolve())
            write_or_print({"recorded_chunks": count}, None)
        elif args.command == "search":
            additions = search_chunks(
                args.work_dir.resolve(), args.query, args.limit, args.after, args.before
            )
            write_or_print({"added_chunks": len(additions), "chunks": additions}, None)
        elif args.command == "summary-next":
            write_or_print(next_period_summary(args.work_dir.resolve()), args.output)
        elif args.command == "record-summary":
            period = record_period_summary(args.work_dir.resolve(), args.input.resolve())
            write_or_print({"recorded_period": period}, None)
        elif args.command == "overall-input":
            write_or_print(overall_input(args.work_dir.resolve()), args.output)
        elif args.command == "record-overall":
            record_overall(args.work_dir.resolve(), args.input.resolve())
            write_or_print({"recorded": "overall"}, None)
        elif args.command == "build":
            build_report(
                args.work_dir, args.output, keep_work=args.keep_work, force=args.force
            )
            output = args.output.resolve()
            write_or_print({"full_report": str(output), "core_report": str(core_report_path(output))}, None)
        elif args.command == "self-test":
            self_test()
        return 0
    except (ExtractorError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
