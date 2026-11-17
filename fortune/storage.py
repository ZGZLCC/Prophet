"""Independent SQLite storage for the embedded fortune workspace."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4


SCHEMA_VERSION = 4
SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reading_sessions (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, type TEXT NOT NULL,
  question TEXT NOT NULL, category TEXT, local_datetime TEXT NOT NULL,
  timezone TEXT NOT NULL, utc_datetime TEXT NOT NULL, location_json TEXT,
  tags_json TEXT NOT NULL, favorite INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS engine_runs (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES reading_sessions(id) ON DELETE CASCADE,
  engine_id TEXT NOT NULL, engine_version TEXT NOT NULL, rule_profile_id TEXT NOT NULL,
  input_json TEXT NOT NULL, facts_json TEXT NOT NULL, rules_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL, input_hash TEXT NOT NULL, facts_hash TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interpretations (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, engine_run_id TEXT NOT NULL REFERENCES engine_runs(id) ON DELETE CASCADE,
  provider TEXT NOT NULL, model TEXT, adapter TEXT, prompt_profile_id TEXT NOT NULL,
  prompt_version TEXT NOT NULL, evidence_hash TEXT NOT NULL, content_markdown TEXT NOT NULL,
  citation_validation_json TEXT NOT NULL, finish_reason TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS syntheses (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES reading_sessions(id) ON DELETE CASCADE,
  engine_run_ids_json TEXT NOT NULL, provider TEXT NOT NULL, model TEXT, adapter TEXT,
  prompt_profile_id TEXT NOT NULL, prompt_version TEXT NOT NULL, facts_hashes_json TEXT NOT NULL,
  content_markdown TEXT NOT NULL, citation_validation_json TEXT NOT NULL, finish_reason TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS forecast_claims (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES reading_sessions(id) ON DELETE CASCADE,
  engine_run_id TEXT NOT NULL REFERENCES engine_runs(id) ON DELETE CASCADE, statement TEXT NOT NULL,
  target_at TEXT, dimensions_json TEXT NOT NULL, status TEXT NOT NULL, locked_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, target_start TEXT, target_end TEXT,
  observable_criteria TEXT, direction TEXT, confidence_label TEXT, tags_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS outcomes (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, claim_id TEXT NOT NULL REFERENCES forecast_claims(id) ON DELETE CASCADE,
  status TEXT NOT NULL, observed_at TEXT NOT NULL, note TEXT NOT NULL, evidence TEXT, created_at TEXT NOT NULL, reviewed_at TEXT
);
CREATE TABLE IF NOT EXISTS person_profiles (
  id TEXT PRIMARY KEY, schema_version TEXT NOT NULL, display_name TEXT NOT NULL, gender TEXT NOT NULL,
  calendar_type TEXT NOT NULL, birth_at TEXT NOT NULL, lunar_date_json TEXT, timezone TEXT NOT NULL,
  location_json TEXT, use_true_solar_time INTEGER NOT NULL, time_policy_id TEXT NOT NULL,
  luck_direction TEXT NOT NULL, start_luck_method TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fortune_runs_session ON engine_runs(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_fortune_claims_session ON forecast_claims(session_id, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_db(path: str | Path) -> None:
    with closing(connect(path)) as connection, connection:
        connection.executescript(SCHEMA)
        for version, name in ((1,"initial-reading-record-v2"),(2,"forecast-claims-outcomes"),(3,"person-profiles"),(4,"stage6-lab-fields-and-syntheses")):
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations VALUES (?, ?, ?)",
                (version, name, _now()),
            )


def _json(value: str | None, fallback: Any) -> Any:
    return json.loads(value) if value else fallback


def list_readings(path: str | Path, *, limit: int = 100) -> list[dict[str, Any]]:
    init_db(path)
    with closing(connect(path)) as connection:
        sessions = connection.execute(
            "SELECT * FROM reading_sessions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        result = []
        for session in sessions:
            item = dict(session)
            item["tags"] = _json(item.pop("tags_json"), [])
            item["runs"] = []
            for row in connection.execute("SELECT * FROM engine_runs WHERE session_id = ? ORDER BY created_at", (item["id"],)):
                run = {**dict(row), "input": _json(row["input_json"], {}), "facts": _json(row["facts_json"], {})}
                run["interpretations"] = [
                    {**dict(interpretation), "citation_validation": _json(interpretation["citation_validation_json"], {})}
                    for interpretation in connection.execute(
                        "SELECT * FROM interpretations WHERE engine_run_id = ? ORDER BY created_at", (run["id"],)
                    )
                ]
                item["runs"].append(run)
            result.append(item)
        return result


def delete_reading(path: str | Path, reading_id: str) -> bool:
    with closing(connect(path)) as connection, connection:
        return connection.execute("DELETE FROM reading_sessions WHERE id = ?", (reading_id,)).rowcount == 1


def save_reading(path: str | Path, *, question: str, category: str, engine_id: str, engine_version: str,
                 rule_profile_id: str, inputs: dict[str, Any], facts: dict[str, Any], timezone_name: str = "Asia/Shanghai") -> str:
    """Save one calculation in the independent fortune database."""
    import hashlib
    session_id, run_id, now = str(uuid4()), str(uuid4()), _now()
    compact = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    input_json, facts_json = compact(inputs), compact(facts)
    init_db(path)
    with closing(connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO reading_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, "fortune-reading-record.v2", "single", question, category, now, timezone_name, now,
             None, "[]", 0, now, now),
        )
        connection.execute(
            "INSERT INTO engine_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, "fortune-engine-run.v2", session_id, engine_id, engine_version, rule_profile_id,
             input_json, facts_json, compact(facts.get("ruleHits", [])), "[]",
             "sha256:" + hashlib.sha256(input_json.encode()).hexdigest(),
             "sha256:" + hashlib.sha256(facts_json.encode()).hexdigest(), now),
        )
    return session_id


def save_interpretation(path: str | Path, *, session_id: str, content_markdown: str,
                        provider: str = "configured-model", model: str | None = None) -> str:
    content = str(content_markdown or "").strip()
    if not content:
        raise ValueError("解读内容为空")
    interpretation_id, now = str(uuid4()), _now()
    init_db(path)
    with closing(connect(path)) as connection, connection:
        run = connection.execute(
            "SELECT id, facts_hash FROM engine_runs WHERE session_id = ? ORDER BY created_at LIMIT 1", (session_id,)
        ).fetchone()
        if not run:
            raise ValueError("所选盘面不存在")
        connection.execute(
            """INSERT INTO interpretations
            (id, schema_version, engine_run_id, provider, model, adapter, prompt_profile_id,
             prompt_version, evidence_hash, content_markdown, citation_validation_json, finish_reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (interpretation_id, "fortune-interpretation.v1", run["id"], provider, model,
             "fortune.knowledge.interpret", "fortune-interpretation-v1", "1",
             run["facts_hash"], content, "{}", None, now),
        )
    return interpretation_id


def list_profiles(path: str | Path) -> list[dict[str, Any]]:
    init_db(path)
    with closing(connect(path)) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM person_profiles ORDER BY updated_at DESC")]


def save_profile(path: str | Path, *, display_name: str, gender: str, birth_at: str,
                 time_policy_id: str = "traditional-zi-chu-li-chun-v1") -> str:
    if not display_name.strip():
        raise ValueError("请填写姓名或代称")
    profile_id, now = str(uuid4()), _now()
    init_db(path)
    with closing(connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO person_profiles VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (profile_id, "fortune-person-profile.v1", display_name.strip(), gender, "gregorian", birth_at, None,
             "Asia/Shanghai", None, 0, time_policy_id, "auto-gender-year-stem", "days-divided-by-three", now, now),
        )
    return profile_id


def update_profile(path: str | Path, profile_id: str, *, display_name: str, gender: str,
                   birth_at: str, time_policy_id: str) -> bool:
    if not display_name.strip():
        raise ValueError("请填写姓名或代称")
    with closing(connect(path)) as connection, connection:
        return connection.execute(
            "UPDATE person_profiles SET display_name=?, gender=?, birth_at=?, time_policy_id=?, updated_at=? WHERE id=?",
            (display_name.strip(), gender, birth_at, time_policy_id, _now(), profile_id),
        ).rowcount == 1


def delete_profile(path: str | Path, profile_id: str) -> bool:
    with closing(connect(path)) as connection, connection:
        return connection.execute("DELETE FROM person_profiles WHERE id=?", (profile_id,)).rowcount == 1


def save_claim(path: str | Path, *, session_id: str, statement: str, target_at: str | None = None) -> str:
    claim_id, now = str(uuid4()), _now()
    with closing(connect(path)) as connection, connection:
        run = connection.execute("SELECT id FROM engine_runs WHERE session_id=? ORDER BY created_at LIMIT 1", (session_id,)).fetchone()
        if not run: raise ValueError("所选盘面不存在")
        connection.execute(
            "INSERT INTO forecast_claims (id,schema_version,session_id,engine_run_id,statement,target_at,dimensions_json,status,created_at,updated_at,tags_json) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (claim_id,"fortune-forecast-claim.v1",session_id,run[0],statement,target_at,"{}","open",now,now,"[]"),
        )
    return claim_id


def save_outcome(path: str | Path, *, claim_id: str, status: str, note: str) -> str:
    outcome_id, now = str(uuid4()), _now()
    with closing(connect(path)) as connection, connection:
        connection.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?,?)", (outcome_id,"fortune-outcome.v1",claim_id,status,now,note,None,now,now))
        connection.execute("UPDATE forecast_claims SET status=?, updated_at=? WHERE id=?", (status,now,claim_id))
    return outcome_id


def list_claims(path: str | Path) -> list[dict[str, Any]]:
    with closing(connect(path)) as connection:
        return [dict(row) for row in connection.execute("SELECT * FROM forecast_claims ORDER BY created_at DESC")]


def backup_database(path: str | Path, destination: str | Path) -> Path:
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as source, closing(sqlite3.connect(destination)) as target:
        source.backup(target)
    return destination


def verify_database(path: str | Path) -> dict[str, Any]:
    with closing(sqlite3.connect(path)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        version = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()[0]
        counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("reading_sessions", "engine_runs", "person_profiles")
        }
    return {"ok": integrity == "ok" and version == SCHEMA_VERSION, "integrity": integrity, "schemaVersion": version, "counts": counts}


def import_database(source_path: str | Path, destination_path: str | Path) -> dict[str, int]:
    """Import old FortuneTelling rows without merging its database file."""
    source_path, destination_path = Path(source_path), Path(destination_path)
    if not source_path.is_file():
        raise ValueError("请选择有效的 FortuneTelling SQLite 数据库")
    with closing(sqlite3.connect(source_path)) as source:
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"reading_sessions", "engine_runs", "schema_migrations"}
        if not required <= tables or source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("数据库不是有效的 FortuneTelling 数据库或已经损坏")
    init_db(destination_path)
    imported: dict[str, int] = {}
    order = ("reading_sessions", "engine_runs", "interpretations", "syntheses", "forecast_claims", "outcomes", "person_profiles")
    with closing(connect(destination_path)) as target:
        target.execute("ATTACH DATABASE ? AS source_db", (str(source_path.resolve()),))
        try:
            source_tables = {row[0] for row in target.execute("SELECT name FROM source_db.sqlite_master WHERE type='table'")}
            for table in order:
                if table not in source_tables:
                    continue
                columns = [row[1] for row in target.execute(f"PRAGMA table_info({table})")]
                source_columns = {row[1] for row in target.execute(f"PRAGMA source_db.table_info({table})")}
                shared = [column for column in columns if column in source_columns]
                names = ", ".join(f'"{column}"' for column in shared)
                before = target.total_changes
                target.execute(f"INSERT OR IGNORE INTO {table} ({names}) SELECT {names} FROM source_db.{table}")
                imported[table] = target.total_changes - before
            target.commit()
        finally:
            target.execute("DETACH DATABASE source_db")
    return imported
