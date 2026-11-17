"""SQLite persistence for the local sentiment-analysis app."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from collections.abc import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS people (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    entry_type TEXT NOT NULL CHECK (entry_type IN ('text', 'document', 'actual_outcome')),
    source_name TEXT NOT NULL DEFAULT '',
    occurred_at TEXT,
    context TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    analysis_json TEXT,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_entries_person_id ON entries(person_id);

CREATE TABLE IF NOT EXISTS profiles (
    person_id INTEGER PRIMARY KEY,
    version INTEGER NOT NULL DEFAULT 0,
    profile_json TEXT NOT NULL DEFAULT '{}',
    summary_md TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS profile_revisions (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    profile_json TEXT NOT NULL,
    summary_md TEXT NOT NULL DEFAULT '',
    trigger_entry_id INTEGER,
    created_at TEXT NOT NULL,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE,
    FOREIGN KEY (trigger_entry_id) REFERENCES entries(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_profile_revisions_person_id
    ON profile_revisions(person_id);

CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL,
    profile_version INTEGER NOT NULL,
    event_text TEXT NOT NULL,
    prediction_json TEXT NOT NULL,
    actual_outcome TEXT,
    review_json TEXT,
    created_at TEXT NOT NULL,
    reviewed_at TEXT,
    FOREIGN KEY (person_id) REFERENCES people(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_predictions_person_id ON predictions(person_id);
"""


class DuplicateEntryError(ValueError):
    """Raised when one person already has the same normalized material."""

    def __init__(self, entry: dict):
        self.entry = entry
        super().__init__(f"该人物已有相同材料（材料 #{entry['id']}）")


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a configured SQLite connection."""

    if str(db_path) == ":memory:":
        connection = sqlite3.connect(":memory:")
    else:
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if str(db_path) != ":memory:":
        connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(db_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Run a group of database changes atomically."""

    connection = connect(db_path)
    try:
        connection.execute("BEGIN")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db(db_path: str | Path) -> None:
    """Create the schema if it does not exist."""

    connection = connect(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_text(content: str) -> str:
    """Normalize line endings and trailing whitespace before storage/hash checks."""

    if not isinstance(content, str):
        raise ValueError("材料内容必须是文字")
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in content.split("\n")).strip()


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_text(content).encode("utf-8")).hexdigest()


def _person_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("人物名称不能为空")
    return name.strip()


def _notes(notes: str | None) -> str:
    return notes.strip() if isinstance(notes, str) else ""


def _as_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _profile_from_row(row: sqlite3.Row | None) -> dict | None:
    profile = _as_dict(row)
    if profile is not None:
        profile["profile"] = json.loads(profile["profile_json"])
    return profile


def _profile_revision_from_row(row: sqlite3.Row | None) -> dict | None:
    revision = _as_dict(row)
    if revision is not None:
        revision["profile"] = json.loads(revision["profile_json"])
    return revision


def _prediction_from_row(row: sqlite3.Row | None) -> dict | None:
    prediction = _as_dict(row)
    if prediction is not None:
        prediction["prediction"] = json.loads(prediction["prediction_json"])
        prediction["review"] = (
            json.loads(prediction["review_json"])
            if prediction["review_json"]
            else None
        )
    return prediction


def _entry_from_row(row: sqlite3.Row | None) -> dict | None:
    entry = _as_dict(row)
    if entry is not None and entry["analysis_json"]:
        entry["analysis"] = json.loads(entry["analysis_json"])
    return entry


def create_person(db_path: str | Path, name: str, notes: str = "") -> int:
    """Create a person and return its id."""

    timestamp = _now()
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO people (name, notes, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (_person_name(name), _notes(notes), timestamp, timestamp),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def list_people(db_path: str | Path) -> list[dict]:
    """Return all people in stable display order."""

    connection = connect(db_path)
    try:
        rows = connection.execute(
            "SELECT id, name, notes, created_at, updated_at "
            "FROM people ORDER BY name COLLATE NOCASE, id"
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def get_person(db_path: str | Path, person_id: int) -> dict | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT id, name, notes, created_at, updated_at FROM people WHERE id = ?",
            (person_id,),
        ).fetchone()
        return _as_dict(row)
    finally:
        connection.close()


def find_duplicate(
    db_path: str | Path, person_id: int, digest: str
) -> dict | None:
    connection = connect(db_path)
    try:
        return _find_duplicate(connection, person_id, digest)
    finally:
        connection.close()


def _find_duplicate(
    connection: sqlite3.Connection, person_id: int, digest: str
) -> dict | None:
    row = connection.execute(
        """
        SELECT id, source_name, occurred_at, created_at
        FROM entries
        WHERE person_id = ? AND content_hash = ?
        ORDER BY id
        LIMIT 1
        """,
        (person_id, digest),
    ).fetchone()
    return _as_dict(row)


def find_duplicate_in_connection(
    connection: sqlite3.Connection, person_id: int, digest: str
) -> dict | None:
    return _find_duplicate(connection, person_id, digest)


def insert_entry(
    connection: sqlite3.Connection,
    *,
    person_id: int,
    entry_type: str,
    source_name: str,
    occurred_at: str | None,
    context: str,
    content: str,
    analysis: dict | None = None,
) -> int:
    normalized_content = normalize_text(content)
    if not normalized_content:
        raise ValueError("材料内容不能为空")
    cursor = connection.execute(
        """
        INSERT INTO entries
            (person_id, entry_type, source_name, occurred_at, context,
             content, content_hash, analysis_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            person_id,
            entry_type,
            (source_name or "").strip(),
            occurred_at,
            (context or "").strip(),
            normalized_content,
            content_hash(normalized_content),
            json.dumps(analysis, ensure_ascii=False) if analysis is not None else None,
            _now(),
        ),
    )
    return int(cursor.lastrowid)


def update_entry_analysis(
    connection: sqlite3.Connection, entry_id: int, analysis: dict
) -> None:
    connection.execute(
        "UPDATE entries SET analysis_json = ? WHERE id = ?",
        (json.dumps(analysis, ensure_ascii=False), entry_id),
    )


def list_entry_ids(connection: sqlite3.Connection, person_id: int) -> list[int]:
    rows = connection.execute(
        "SELECT id FROM entries WHERE person_id = ? ORDER BY id", (person_id,)
    ).fetchall()
    return [int(row["id"]) for row in rows]


def _list_entries(connection: sqlite3.Connection, person_id: int) -> list[dict]:
    rows = connection.execute(
        """
        SELECT * FROM entries
        WHERE person_id = ?
        ORDER BY COALESCE(occurred_at, created_at) DESC, id DESC
        """,
        (person_id,),
    ).fetchall()
    return [_entry_from_row(row) for row in rows]


def list_entries_in_connection(
    connection: sqlite3.Connection, person_id: int
) -> list[dict]:
    return _list_entries(connection, person_id)


def list_entries(db_path: str | Path, person_id: int) -> list[dict]:
    connection = connect(db_path)
    try:
        return _list_entries(connection, person_id)
    finally:
        connection.close()


def get_entry(db_path: str | Path, entry_id: int) -> dict | None:
    connection = connect(db_path)
    try:
        row = connection.execute(
            "SELECT * FROM entries WHERE id = ?", (entry_id,)
        ).fetchone()
        return _entry_from_row(row)
    finally:
        connection.close()


def set_entry_active(
    db_path: str | Path, person_id: int, entry_id: int, is_active: bool
) -> bool:
    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            UPDATE entries
            SET is_active = ?
            WHERE id = ? AND person_id = ?
            """,
            (1 if is_active else 0, entry_id, person_id),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def insert_prediction(
    connection: sqlite3.Connection,
    *,
    person_id: int,
    profile_version: int,
    event_text: str,
    prediction: dict,
) -> int:
    normalized_event = normalize_text(event_text)
    if not normalized_event:
        raise ValueError("预测事件不能为空")
    if int(profile_version) < 1:
        raise ValueError("画像版本无效")
    cursor = connection.execute(
        """
        INSERT INTO predictions
            (person_id, profile_version, event_text, prediction_json, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            person_id,
            int(profile_version),
            normalized_event,
            json.dumps(prediction, ensure_ascii=False),
            _now(),
        ),
    )
    return int(cursor.lastrowid)


def _get_prediction(
    connection: sqlite3.Connection,
    prediction_id: int,
    person_id: int | None = None,
) -> dict | None:
    if person_id is None:
        row = connection.execute(
            "SELECT * FROM predictions WHERE id = ?", (prediction_id,)
        ).fetchone()
    else:
        row = connection.execute(
            "SELECT * FROM predictions WHERE id = ? AND person_id = ?",
            (prediction_id, person_id),
        ).fetchone()
    return _prediction_from_row(row)


def get_prediction(db_path: str | Path, prediction_id: int) -> dict | None:
    connection = connect(db_path)
    try:
        return _get_prediction(connection, prediction_id)
    finally:
        connection.close()


def get_prediction_in_connection(
    connection: sqlite3.Connection,
    prediction_id: int,
    person_id: int | None = None,
) -> dict | None:
    return _get_prediction(connection, prediction_id, person_id)


def list_predictions(db_path: str | Path, person_id: int) -> list[dict]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT * FROM predictions
            WHERE person_id = ?
            ORDER BY id DESC
            """,
            (person_id,),
        ).fetchall()
        return [_prediction_from_row(row) for row in rows]
    finally:
        connection.close()


def update_prediction_review(
    connection: sqlite3.Connection,
    *,
    prediction_id: int,
    person_id: int,
    actual_outcome: str,
    review: dict,
) -> None:
    normalized_outcome = normalize_text(actual_outcome)
    if not normalized_outcome:
        raise ValueError("实际结果不能为空")
    cursor = connection.execute(
        """
        UPDATE predictions
        SET actual_outcome = ?, review_json = ?, reviewed_at = ?
        WHERE id = ? AND person_id = ? AND actual_outcome IS NULL
        """,
        (
            normalized_outcome,
            json.dumps(review, ensure_ascii=False),
            _now(),
            prediction_id,
            person_id,
        ),
    )
    if cursor.rowcount != 1:
        raise ValueError("预测不存在，或已经完成复盘")


def delete_prediction(
    db_path: str | Path, person_id: int, prediction_id: int
) -> bool:
    """Delete one person's prediction record, retaining any actual-outcome entry."""

    connection = connect(db_path)
    try:
        cursor = connection.execute(
            "DELETE FROM predictions WHERE id = ? AND person_id = ?",
            (prediction_id, person_id),
        )
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def get_profile(db_path: str | Path, person_id: int) -> dict | None:
    connection = connect(db_path)
    try:
        return _get_profile(connection, person_id)
    finally:
        connection.close()


def _get_profile(connection: sqlite3.Connection, person_id: int) -> dict | None:
    row = connection.execute(
        "SELECT * FROM profiles WHERE person_id = ?", (person_id,)
    ).fetchone()
    return _profile_from_row(row)


def get_profile_in_connection(
    connection: sqlite3.Connection, person_id: int
) -> dict | None:
    return _get_profile(connection, person_id)


def get_profile_revision(
    db_path: str | Path, person_id: int, version: int
) -> dict | None:
    connection = connect(db_path)
    try:
        return get_profile_revision_in_connection(connection, person_id, version)
    finally:
        connection.close()


def get_profile_revision_in_connection(
    connection: sqlite3.Connection, person_id: int, version: int
) -> dict | None:
    row = connection.execute(
        """
        SELECT * FROM profile_revisions
        WHERE person_id = ? AND version = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (person_id, int(version)),
    ).fetchone()
    return _profile_revision_from_row(row)


def list_profile_revisions(db_path: str | Path, person_id: int) -> list[dict]:
    connection = connect(db_path)
    try:
        rows = connection.execute(
            """
            SELECT * FROM profile_revisions
            WHERE person_id = ?
            ORDER BY version DESC, id DESC
            """,
            (person_id,),
        ).fetchall()
        return [_profile_revision_from_row(row) for row in rows]
    finally:
        connection.close()


def save_profile(
    connection: sqlite3.Connection,
    *,
    person_id: int,
    profile: dict,
    summary_md: str,
    trigger_entry_id: int | None,
) -> int:
    current = connection.execute(
        "SELECT version FROM profiles WHERE person_id = ?", (person_id,)
    ).fetchone()
    version = int(current["version"]) + 1 if current else 1
    timestamp = _now()
    profile_json = json.dumps(profile, ensure_ascii=False)

    if current:
        connection.execute(
            """
            UPDATE profiles
            SET version = ?, profile_json = ?, summary_md = ?, updated_at = ?
            WHERE person_id = ?
            """,
            (version, profile_json, summary_md, timestamp, person_id),
        )
    else:
        connection.execute(
            """
            INSERT INTO profiles
                (person_id, version, profile_json, summary_md, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (person_id, version, profile_json, summary_md, timestamp),
        )

    connection.execute(
        """
        INSERT INTO profile_revisions
            (person_id, version, profile_json, summary_md, trigger_entry_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (person_id, version, profile_json, summary_md, trigger_entry_id, timestamp),
    )
    return version


def update_person(
    db_path: str | Path, person_id: int, name: str, notes: str = ""
) -> None:
    """Update a person's display name and notes."""

    connection = connect(db_path)
    try:
        cursor = connection.execute(
            """
            UPDATE people
            SET name = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (_person_name(name), _notes(notes), _now(), person_id),
        )
        if cursor.rowcount != 1:
            raise KeyError(f"人物不存在: {person_id}")
        connection.commit()
    finally:
        connection.close()


def delete_person(db_path: str | Path, person_id: int) -> bool:
    """Delete a person and all related records via foreign-key cascades."""

    connection = connect(db_path)
    try:
        cursor = connection.execute("DELETE FROM people WHERE id = ?", (person_id,))
        connection.commit()
        return cursor.rowcount == 1
    finally:
        connection.close()


def export_person(db_path: str | Path, person_id: int) -> dict | None:
    person = get_person(db_path, person_id)
    if person is None:
        return None
    return {
        "export_version": 1,
        "person": person,
        "profile": get_profile(db_path, person_id),
        "profile_revisions": list_profile_revisions(db_path, person_id),
        "entries": list_entries(db_path, person_id),
        "predictions": list_predictions(db_path, person_id),
    }


def backup_database(db_path: str | Path) -> bytes:
    """Return a consistent SQLite backup without leaving a backup file behind."""

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temporary:
        backup_path = Path(temporary.name)
    source = connect(db_path)
    destination = sqlite3.connect(backup_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    try:
        return backup_path.read_bytes()
    finally:
        backup_path.unlink(missing_ok=True)


def restore_database(db_path: str | Path, data: bytes) -> None:
    """Validate and restore a Prophet SQLite backup over the current database."""

    if not isinstance(data, bytes) or not data.startswith(b"SQLite format 3\x00"):
        raise ValueError("所选文件不是有效的 SQLite 数据库")
    required_tables = {
        "people",
        "entries",
        "profiles",
        "profile_revisions",
        "predictions",
    }
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temporary:
        backup_path = Path(temporary.name)
        temporary.write(data)
    source = None
    destination = None
    try:
        source = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True)
        if source.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("数据库完整性检查未通过")
        tables = {
            row[0]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing = required_tables - tables
        if missing:
            raise ValueError(f"数据库缺少 Prophet 数据表：{', '.join(sorted(missing))}")
        if source.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('trigger', 'view') LIMIT 1"
        ).fetchone():
            raise ValueError("数据库包含不受支持的触发器或视图")
        for table, column in (
            ("entries", "analysis_json"),
            ("profiles", "profile_json"),
            ("profile_revisions", "profile_json"),
            ("predictions", "prediction_json"),
            ("predictions", "review_json"),
        ):
            for (value,) in source.execute(
                f"SELECT {column} FROM {table} WHERE {column} IS NOT NULL"
            ):
                json.loads(value)
        destination = connect(db_path)
        source.backup(destination)
        destination.commit()
    except json.JSONDecodeError as error:
        raise ValueError("数据库包含损坏的分析数据") from error
    except sqlite3.DatabaseError as error:
        raise ValueError(f"无法读取数据库：{error}") from error
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        backup_path.unlink(missing_ok=True)
