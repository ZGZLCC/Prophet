"""Python bridge exposed to the local pywebview page.

The public method names stay in this module through the composed ``AppApi``
class; implementation is grouped by feature under :mod:`api`.
"""

from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from api.base import PROJECT_ROOT, ApiBase
from api.chat import ChatApiMixin
from api.dialogs import DialogApiMixin
from api.fortune import FortuneApiMixin
from api.profile import ProfileApiMixin
from api.settings import SettingsApiMixin
from person_profile import analysis


class AppApi(
    ApiBase,
    SettingsApiMixin,
    ProfileApiMixin,
    ChatApiMixin,
    FortuneApiMixin,
    DialogApiMixin,
):
    """The only Python object exposed to the local web page."""


def run_self_test() -> None:
    api = AppApi(resource_root=PROJECT_ROOT, app_home=PROJECT_ROOT)
    assert api.get_app_info()["data"]["streamlit"] is False
    assert api.health_check()["ok"] is True
    assert api._mask_key("abcd1234") == "•••• 1234"
    try:
        api._resolve_directory("bad\npath", "目录")
    except ValueError:
        pass
    else:
        raise AssertionError("newline path was accepted")
    invalid = api.save_settings(
        {"provider": "unsupported", "model": "demo", "api_key": "demo"}
    )
    assert invalid["ok"] is False
    assert invalid["error"]["code"] == "SETTINGS_SAVE_FAILED"

    with tempfile.TemporaryDirectory(prefix="prophet-api-self-test-") as temporary:
        test_home = Path(temporary)
        (test_home / ".env").write_text(
            f"PROPHET_DATABASE_DIR={test_home / 'data'}\n",
            encoding="utf-8",
        )
        test_api = AppApi(resource_root=PROJECT_ROOT, app_home=test_home)
        empty_health = test_api.health_check()
        assert empty_health["ok"] and empty_health["data"]["status"] == "ok"
        assert empty_health["data"]["database_summary"] == "本地数据库状态正常"
        assert all(item["status"] == "empty" for item in empty_health["data"]["databases"])
        appearance = test_api.save_appearance_settings(
            {"theme": "dark", "timezone": "America/New_York"}
        )
        assert appearance["ok"] and appearance["data"]["timezone"] == "America/New_York"
        saved_appearance = analysis.read_local_env(test_home / ".env")
        assert saved_appearance["PROPHET_THEME"] == "dark"
        assert saved_appearance["PROPHET_TIMEZONE"] == "America/New_York"
        created = test_api.create_person("自检人物", "桥接层自检")
        assert created["ok"] is True
        person_id = created["data"]["person"]["id"]
        assert test_api.list_people()["data"][0]["name"] == "自检人物"
        assert test_api.get_person_workspace(person_id)["data"]["entries"] == []
        updated = test_api.update_person(person_id, "自检人物 2", "更新后的备注")
        assert updated["ok"] and updated["data"]["person"]["name"] == "自检人物 2"
        assert test_api.update_person(person_id, "自检人物 2", "字" * 101)["ok"] is False
        material_path = test_home / "sample.txt"
        material_path.write_text("本地预览材料", encoding="utf-8")
        preview = test_api.preview_material(str(material_path))
        assert preview["ok"] and preview["data"]["content"] == "本地预览材料"
        chat_path = test_home / "chat.jsonl"
        chat_path.write_text(
            "\n".join(
                json.dumps(item, ensure_ascii=False)
                for item in (
                    {"sender": "甲", "text": "先说清楚", "time": "2024-01-01T10:00:00+08:00"},
                    {"sender": "乙", "text": "好", "time": "2024-01-01T10:01:00+08:00"},
                    {"sender": "甲", "text": "", "time": "2024-01-01T10:02:00+08:00"},
                )
            )
            + "\n",
            encoding="utf-8",
        )
        inspected = test_api.inspect_chat(str(chat_path))
        assert inspected["ok"] and inspected["data"] == {
            "valid_text_messages": 2,
            "skipped_records": 1,
            "senders": {"甲": 1, "乙": 1},
        }
        prompt = test_api.get_chat_agent_prompt(
            str(chat_path), "甲", str(test_home / "reports"), "冲突"
        )
        assert prompt["ok"] and "目标人物 sender：甲" in prompt["data"]["prompt"]
        commands = test_api.get_chat_manual_commands(
            str(chat_path), "甲", str(test_home / "reports"), "冲突"
        )
        assert commands["ok"] and "record-summary" in commands["data"]["commands"]
        invalid_dates = test_api.start_chat_export(
            {
                "source": "qq",
                "output_format": "json",
                "start_time": "2024-02-01",
                "end_time": "2024-01-01",
                "output_dir": str(test_home / "out"),
            }
        )
        assert invalid_dates["ok"] is False
        assert invalid_dates["error"]["code"] == "CHAT_EXPORT_START_FAILED"

        fixed_cast_at = "2026-08-23T12:00:00+08:00"
        fortune_payloads = (
            {"engine": "zhouyi-textual", "question": "固定周易", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"castAt": fixed_cast_at, "lines": [6, 7, 8, 9, 7, 8]}},
            {"engine": "meihua-yishu", "question": "固定梅花", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"method": "manual", "upper": 3, "lower": 6, "moving": 2}},
            {"engine": "liuyao-najia", "question": "固定六爻", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"castAt": fixed_cast_at, "lines": [6, 7, 8, 9, 7, 8], "useGodLine": 1}},
            {"engine": "bazi-ziping", "question": "固定八字", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"birthAt": "1990-01-01T08:00:00+08:00", "gender": "unspecified", "flowYearCount": 1}},
            {"engine": "ziwei", "question": "固定紫微", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"birthAt": "1990-01-01T08:00:00+08:00", "gender": "female", "flowYearCount": 1}},
            {"engine": "qimen", "question": "固定奇门", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"castAt": fixed_cast_at}},
            {"engine": "liuren", "question": "固定六壬", "category": "career", "policy": "traditional-zi-chu-li-chun-v1", "values": {"castAt": fixed_cast_at}},
        )
        fortune_results = [test_api.calculate_fortune(payload) for payload in fortune_payloads]
        assert all(item["ok"] for item in fortune_results)
        assert fortune_results[0]["data"]["facts"]["primary"]["number"] == 47
        fortune_history = test_api.get_fortune_workspace()["data"]["readings"]
        assert len(fortune_history) == 7
        assert {item["runs"][0]["engine_id"] for item in fortune_history} == {
            payload["engine"] for payload in fortune_payloads
        }
        first_reading = fortune_results[0]["data"]["reading_id"]
        prompt = test_api.get_fortune_agent_prompt(first_reading)
        assert prompt["ok"] and "<FACTS>" in prompt["data"]["prompt"]
        assert fortune_results[5]["data"]["facts"]["ruleHits"]
        knowledge = test_api.search_fortune_knowledge("十神", "bazi-ziping")
        assert knowledge["ok"] and knowledge["data"]
        fortune_status = test_api.verify_fortune_database()
        assert fortune_status["ok"] and fortune_status["data"]["ok"] is True
        profile = test_api.create_fortune_profile(
            {
                "display_name": "命主自检",
                "gender": "female",
                "birth_at": "1990-01-01T08:00:00+08:00",
            }
        )
        assert profile["ok"]
        profile_reading = test_api.calculate_fortune(
            {
                "engine": "bazi-ziping",
                "question": "档案起盘",
                "values": {"profileId": profile["data"]["id"], "flowYearCount": 1},
            }
        )
        assert profile_reading["ok"] and profile_reading["data"]["input"]["profileId"] == profile["data"]["id"]
        claim = test_api.create_fortune_claim(first_reading, "固定预测陈述", "2026-09-01")
        assert claim["ok"]
        outcome = test_api.save_fortune_outcome(
            claim["data"]["claim_id"], "hit", "固定结果"
        )
        assert outcome["ok"] and test_api.get_fortune_workspace()["data"]["claims"][0]["status"] == "hit"
        report = test_api.export_fortune_reading(first_reading, str(test_home / "fortune-out"))
        assert report["ok"] and Path(report["data"]["path"]).is_file()
        fortune_backup = test_api.backup_fortune_database(str(test_home / "fortune-out"))
        assert fortune_backup["ok"] and Path(fortune_backup["data"]["path"]).is_file()
        extra_reading = test_api.calculate_fortune(
            {"engine": "zhouyi-textual", "question": "替换后应消失", "values": {}}
        )["data"]["reading_id"]
        imported_fortune = test_api.import_fortune_database(
            fortune_backup["data"]["path"], True
        )
        assert imported_fortune["ok"] and Path(imported_fortune["data"]["database_path"]).is_file()
        assert all(
            item["id"] != extra_reading
            for item in test_api.get_fortune_workspace()["data"]["readings"]
        )
        with closing(sqlite3.connect(test_api._sentiment_db())) as sentiment_connection, closing(
            sqlite3.connect(test_api._fortune_db())
        ) as fortune_connection:
            assert sentiment_connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reading_sessions'"
            ).fetchone() is None
            assert fortune_connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='people'"
            ).fetchone() is None
        checked = test_api.check_material(person_id, "本地预览材料")
        assert checked["ok"] and checked["data"]["characters"] == 6
        exported = test_api.export_person(person_id, "json", str(test_home / "out"))
        assert exported["ok"] and Path(exported["data"]["path"]).is_file()
        backup = test_api.export_person(person_id, "database", str(test_home / "out"))
        assert backup["ok"] and Path(backup["data"]["path"]).is_file()
        test_api.create_person("临时人物")
        restored = test_api.import_database(backup["data"]["path"], True)
        assert restored["ok"] and len(test_api.list_people()["data"]) == 1
        deleted = test_api.delete_person(person_id)
        assert deleted["ok"] and deleted["data"]["deleted"] is True
        task = test_api._submit_task("self-check", lambda: {"done": True})
        with test_api._task_lock:
            test_api._tasks[task["task_id"]][1].result(timeout=2)
        finished = test_api.get_task(task["task_id"])
        assert finished["ok"] and finished["data"]["status"] == "succeeded"
        assert finished["data"]["result"] == {"done": True}

    class FakeWindow:
        def create_file_dialog(self, *args: Any, **kwargs: Any) -> list[str]:
            self.args = args
            self.kwargs = kwargs
            return [str(PROJECT_ROOT / "requirements.txt")]

    window = FakeWindow()
    api.set_window(window)
    selected = api.choose_file(file_types=["Text files (*.txt)"])
    assert selected["ok"] and selected["data"]["paths"] == [
        str(PROJECT_ROOT / "requirements.txt")
    ]
    assert window.kwargs["file_types"] == ("Text files (*.txt)",)
    print("app_api self-check passed")


if __name__ == "__main__":
    run_self_test()
