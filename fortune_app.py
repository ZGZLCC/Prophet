"""UI-independent helpers for the native cyber-fortune workspace."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from datetime import date, datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from fortune.engines import ENGINE_LABELS, calculate
from fortune.storage import save_reading


FORTUNE_TIMEZONE = ZoneInfo("Asia/Shanghai")
GENDERS = {"unspecified": "未指定", "male": "男", "female": "女"}
POLICIES = {
    "traditional-zi-chu-li-chun-v1": "子初换日 · 立春换年",
    "traditional-zi-zheng-li-chun-v1": "子正换日 · 立春换年",
    "civil-standard-time-v1": "民用时间",
}
CATEGORIES = {
    "other": "其他",
    "career": "事业",
    "finance": "财务",
    "relationship": "关系",
    "travel": "出行",
    "lost-item": "失物",
}
LUCK_DIRECTIONS = {
    "auto-gender-year-stem": "按性别与年干自动判断",
    "forward": "顺行",
    "backward": "逆行",
}
MEIHUA_METHODS = {"number": "数字", "time": "时间", "manual": "手动"}
FORTUNE_MAX_TEXT = 2_000


def _text(value: object, label: str, *, required: bool = False, limit: int = FORTUNE_MAX_TEXT) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是文本。")
    value = value.strip()
    if "\x00" in value:
        raise ValueError(f"{label}不能包含空字符。")
    if required and not value:
        raise ValueError(f"{label}不能为空。")
    if len(value) > limit:
        raise ValueError(f"{label}过长。")
    return value


def _integer(value: object, label: str, *, minimum: int, maximum: int, optional: bool = False) -> int | None:
    if value in (None, "") and optional:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{label}必须是整数。")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"{label}必须是整数。")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}必须是整数。") from error
    if result < minimum or result > maximum:
        raise ValueError(f"{label}需在 {minimum}–{maximum} 之间。")
    return result


def _earliest_date(today: date) -> date:
    return date(today.year - 100, today.month, min(today.day, monthrange(today.year - 100, today.month)[1]))


def normalize_datetime(
    value: object, label: str, *, required: bool = True, time_zone: str = "Asia/Shanghai"
) -> str | None:
    text = _text(value, label, required=required, limit=80)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
        selected_zone = ZoneInfo(time_zone)
    except (ValueError, KeyError) as error:
        raise ValueError(f"{label}必须是有效的日期时间。") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=selected_zone)
    parsed = parsed.astimezone(FORTUNE_TIMEZONE)
    now = datetime.now(FORTUNE_TIMEZONE)
    if parsed > now:
        raise ValueError(f"{label}不能晚于当前时间。")
    if not _earliest_date(now.date()) <= parsed.date() <= now.date():
        raise ValueError(f"{label}需在最近 100 年内。")
    return parsed.isoformat(timespec="seconds")


def prepare_profile(payload: Mapping[str, object]) -> dict[str, str]:
    if not isinstance(payload, Mapping):
        raise ValueError("命主档案格式无效。")
    gender = _text(payload.get("gender", "unspecified"), "性别", required=True, limit=32)
    if gender not in GENDERS:
        raise ValueError("性别选项无效。")
    policy = _text(payload.get("time_policy_id", next(iter(POLICIES))), "换日与年界", required=True, limit=80)
    if policy not in POLICIES:
        raise ValueError("换日与年界选项无效。")
    birth_at = normalize_datetime(
        payload.get("birth_at"), "出生时间", time_zone=str(payload.get("timezone", "Asia/Shanghai"))
    )
    return {
        "display_name": _text(payload.get("display_name"), "姓名或代称", required=True),
        "gender": gender,
        "birth_at": birth_at or "",
        "time_policy_id": policy,
    }


def prepare_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Validate native-form input while keeping the seven engine contracts intact."""
    if not isinstance(payload, Mapping):
        raise ValueError("起盘参数格式无效。")
    time_zone = str(payload.get("timezone", "Asia/Shanghai"))
    engine = _text(payload.get("engine"), "术式", required=True, limit=80)
    if engine not in ENGINE_LABELS:
        raise ValueError("术式选项无效。")
    category = _text(payload.get("category", "other"), "分类", required=True, limit=32)
    if category not in CATEGORIES:
        raise ValueError("分类选项无效。")
    policy = _text(payload.get("policy", next(iter(POLICIES))), "换日与年界", required=True, limit=80)
    if policy not in POLICIES:
        raise ValueError("换日与年界选项无效。")
    raw_values = payload.get("values", {})
    if not isinstance(raw_values, Mapping):
        raise ValueError("术式输入格式无效。")
    values = dict(raw_values)
    values["category"] = category
    values["timePolicyId"] = policy
    question = _text(payload.get("question", ""), "所问事项") or "未命名占测"

    if engine == "zhouyi-textual":
        lines = values.get("lines")
        if lines in (None, "", []):
            values.pop("lines", None)
        elif not isinstance(lines, (list, tuple)) or len(lines) != 6:
            raise ValueError("六爻值必须依次填写 6、7、8 或 9。")
        else:
            values["lines"] = [_integer(item, "六爻值", minimum=6, maximum=9) for item in lines]
        values["castAt"] = normalize_datetime(
            values.get("castAt") or datetime.now(FORTUNE_TIMEZONE).isoformat(),
            "起盘时间",
            time_zone=time_zone,
        )
    elif engine == "meihua-yishu":
        method = _text(values.get("method", "number"), "起卦方式", required=True, limit=32)
        if method not in MEIHUA_METHODS:
            raise ValueError("梅花起卦方式无效。")
        values["method"] = method
        if method == "number":
            values["upper"] = _integer(values.get("upper"), "上卦数", minimum=1, maximum=999)
            values["lower"] = _integer(values.get("lower"), "下卦数", minimum=1, maximum=999)
        elif method == "manual":
            values["upper"] = _integer(values.get("upper"), "上卦数", minimum=1, maximum=8)
            values["lower"] = _integer(values.get("lower"), "下卦数", minimum=1, maximum=8)
            values["moving"] = _integer(values.get("moving"), "动爻", minimum=1, maximum=6)
        else:
            values["castAt"] = normalize_datetime(values.get("castAt"), "起盘时间", time_zone=time_zone)
    elif engine == "liuyao-najia":
        values["castAt"] = normalize_datetime(values.get("castAt"), "起盘时间", time_zone=time_zone)
        lines = values.get("lines")
        if lines in (None, "", []):
            values.pop("lines", None)
        elif not isinstance(lines, (list, tuple)) or len(lines) != 6:
            raise ValueError("六爻值必须依次填写 6、7、8 或 9。")
        else:
            values["lines"] = [_integer(item, "六爻值", minimum=6, maximum=9) for item in lines]
        values["useGodLine"] = _integer(values.get("useGodLine"), "用神爻", minimum=1, maximum=6, optional=True)
    elif engine in ("bazi-ziping", "ziwei"):
        values["birthAt"] = normalize_datetime(values.get("birthAt"), "出生时间", time_zone=time_zone)
        gender = _text(values.get("gender", "unspecified"), "性别", required=True, limit=32)
        if gender not in GENDERS:
            raise ValueError("性别选项无效。")
        values["gender"] = gender
        values["flowYearCount"] = _integer(values.get("flowYearCount", 12), "流年数量", minimum=1, maximum=50)
        if engine == "bazi-ziping":
            luck_direction = _text(values.get("luckDirection", "auto-gender-year-stem"), "大运方向", required=True, limit=40)
            if luck_direction not in LUCK_DIRECTIONS:
                raise ValueError("大运方向选项无效。")
            values["luckDirection"] = luck_direction
        else:
            fix_leap = values.get("fixLeap", True)
            if not isinstance(fix_leap, bool):
                raise ValueError("闰月修正选项无效。")
            values["fixLeap"] = fix_leap
            values["flowYearStart"] = _integer(values.get("flowYearStart"), "流年起始年", minimum=1900, maximum=2500, optional=True)
    else:
        values["castAt"] = normalize_datetime(values.get("castAt"), "起盘时间", time_zone=time_zone)

    profile_id = values.get("profileId")
    if profile_id not in (None, ""):
        profile_id = _text(profile_id, "命主档案编号", required=True, limit=100)
        values["profileId"] = profile_id
    return {"engine": engine, "question": question, "category": category, "policy": policy, "values": values}


def calculate_and_save(db_path: str | Path, payload: Mapping[str, object]) -> dict[str, object]:
    prepared = prepare_payload(payload)
    facts = calculate(str(prepared["engine"]), prepared["values"])
    values = prepared["values"]
    if values.get("profileId"):
        facts.setdefault("birth", {}).update(
            profileId=values["profileId"], displayName=values.get("displayName", "")
        )
    reading_id = save_reading(
        db_path,
        question=str(prepared["question"]),
        category=str(prepared["category"]),
        engine_id=str(prepared["engine"]),
        engine_version=str(facts.get("engineVersion", "python-1")),
        rule_profile_id=str(facts.get("ruleProfile", "default")),
        inputs=values,
        facts=facts,
    )
    return {
        "reading_id": reading_id,
        "engine": prepared["engine"],
        "engine_label": ENGINE_LABELS[str(prepared["engine"])],
        "question": prepared["question"],
        "category": prepared["category"],
        "input": values,
        "facts": facts,
    }


def export_reading_report(item: Mapping[str, object], output_dir: str | Path) -> Path:
    runs = item.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ValueError("历史记录没有盘面。")
    run = runs[0]
    if not isinstance(run, Mapping):
        raise ValueError("历史记录格式无效。")
    facts = run.get("facts", {})
    interpretations = run.get("interpretations", [])
    interpretation = ""
    if isinstance(interpretations, list) and interpretations and isinstance(interpretations[-1], Mapping):
        interpretation = str(interpretations[-1].get("content_markdown", ""))
    report = "\n".join(
        (
            f"# {item.get('question', '未命名占测')}",
            f"- 创建时间：{item.get('created_at', '')}",
            f"- 术式：{ENGINE_LABELS.get(str(run.get('engine_id', '')), str(run.get('engine_id', '')))}",
            "",
            "## 输入",
            "```json",
            json.dumps(run.get("input", {}), ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## 盘面",
            "```json",
            json.dumps(facts, ensure_ascii=False, indent=2, default=str),
            "```",
            "",
            "## 解读",
            interpretation or "尚未生成模型解读。",
            "",
        )
    )
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    path = destination / f"fortune-report-{stamp}.md"
    counter = 1
    while path.exists():
        path = destination / f"fortune-report-{stamp}-{counter}.md"
        counter += 1
    path.write_text(report, encoding="utf-8")
    return path


if __name__ == "__main__":
    assert prepare_payload({"engine": "zhouyi-textual", "values": {"lines": [6, 7, 8, 9, 7, 8]}})["values"]["lines"] == [6, 7, 8, 9, 7, 8]
    try:
        prepare_payload({"engine": "meihua-yishu", "values": {"method": "manual", "upper": 9, "lower": 1, "moving": 1}})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid meihua input was accepted")
    print("fortune_app self-check passed")
