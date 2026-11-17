"""Build JSON-backed profile data into a readable Markdown export."""

from __future__ import annotations

import json


PROFILE_LABELS = {
    "emotion_patterns": "常见情绪模式",
    "triggers": "可能的触发因素",
    "behavior_tendencies": "应对方式与行为倾向",
    "communication_preferences": "沟通偏好",
    "values_and_needs": "重视的事物与可能需求",
    "situational_differences": "情境差异与例外",
    "uncertainties_and_contradictions": "不确定或相互矛盾的结论",
}


def _evidence(ids: list[int]) -> str:
    return "、".join(f"#{entry_id}" for entry_id in ids) or "暂无"


def build_markdown_export(bundle: dict) -> str:
    person = bundle["person"]
    lines = [f"# {person['name']}", "", f"- 导出时间：{person['updated_at']}"]
    if person["notes"]:
        lines.extend(("", "## 人物备注", "", person["notes"]))

    profile = bundle["profile"]
    if profile:
        lines.extend(("", f"## 当前画像（版本 {profile['version']}）", ""))
        lines.append(profile["summary_md"])
        for section, label in PROFILE_LABELS.items():
            items = profile["profile"][section]
            if not items:
                continue
            lines.extend(("", f"### {label}"))
            for item in items:
                lines.append(
                    f"- {item['claim']}（{item['kind']}，置信度：{item['confidence']}，"
                    f"证据：{_evidence(item['evidence_entry_ids'])}）"
                )

    lines.extend(("", "## 材料时间线", ""))
    for entry in bundle["entries"]:
        state = "有效" if entry["is_active"] else "已停用"
        lines.extend(
            (
                f"### 材料 #{entry['id']}｜{entry['source_name']}｜{state}",
                f"- 类型：{entry['entry_type']}；创建时间：{entry['created_at']}",
                f"- 发生时间：{entry['occurred_at'] or '未填写'}；备注：{entry['context'] or '无'}",
                "",
                entry["content"],
                "",
            )
        )

    lines.extend(("## 预测与复盘", ""))
    for prediction in bundle["predictions"]:
        lines.extend(
            (
                f"### 预测 #{prediction['id']}｜画像版本 {prediction['profile_version']}",
                f"- 创建时间：{prediction['created_at']}",
                "",
                prediction["event_text"],
                "",
                "```json",
                json.dumps(prediction["prediction"], ensure_ascii=False, indent=2),
                "```",
            )
        )
        if prediction["actual_outcome"] is not None:
            lines.extend(
                (
                    "",
                    "#### 实际结果",
                    "",
                    prediction["actual_outcome"],
                    "",
                    "```json",
                    json.dumps(prediction["review"], ensure_ascii=False, indent=2),
                    "```",
                )
            )

    lines.extend(("", "## 画像版本历史", ""))
    for revision in bundle["profile_revisions"]:
        lines.append(
            f"- 版本 {revision['version']}｜{revision['created_at']}｜"
            f"触发材料：{revision['trigger_entry_id'] or '无（重建/回退）'}"
        )
    return "\n".join(lines).strip() + "\n"
