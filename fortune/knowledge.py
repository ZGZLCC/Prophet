"""Grounded corpus search and the FortuneTelling prompt profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import analysis


CORPUS = Path(__file__).resolve().parent / "data" / "corpus"
ENGINE_CORPUS_FILES = {
    "zhouyi-textual": ("zhouyi", "yizhuan"),
    "meihua-yishu": ("meihua",),
    "liuyao-najia": ("liuyao",),
    "bazi-ziping": ("bazi",),
    "ziwei": ("ziwei",),
    "qimen": ("qimen",),
    "liuren": ("liuren",),
}

PROMPT_PROFILES = {
    "zhouyi-textual": {
        "profile_id": "zhouyi-textual-v2",
        "version": "2.0.0",
        "max_chars": 30_000,
        "system_prompt": """你是“周易经义”模式的辅助解释器。你只能解释服务端提供的 FACTS 和 SOURCES，不得重新排卦、改变卦名、补写原文或把自己的推断冒充古籍。

输出要求：
1. 先用简洁文字复述本卦、之卦和动爻等确定性事实。
2. 结合用户问题给出审慎的经义解释；解释不是古籍原文，使用不确定性语言。
3. 每一个基于 SOURCES 的重要判断，都在句末使用已有来源 ID 的 [source-id] 引用。
4. 只使用提供的来源 ID；没有依据时明确说“现有证据不足以判断”。
5. 不声称用户没有提供的个人事实，不给出绝对吉凶、精确概率或必然应期。
6. 涉及健康、法律、投资、人身安全或重大财务事项时，只给一般性反思，提醒用户咨询合适的专业人士。
7. 不要输出 Markdown 表格，不要伪造来源，不要把 [source-id] 改写成不存在的 ID。

请将“古籍原文”和“结合问题的解释”分开。""",
    },
    "meihua-yishu": {
        "profile_id": "meihua-yishu-v1",
        "version": "1.0.0",
        "max_chars": 8_000,
        "system_prompt": "你是梅花易数研究模式的辅助解释器。只能解释服务端提供的确定性 facts 和规则摘录，不得把体用关系改写为绝对吉凶，不得补造应期或用户未提供的事实。",
    },
    "liuyao-najia": {
        "profile_id": "liuyao-najia-v1",
        "version": "1.0.0",
        "max_chars": 12_000,
        "system_prompt": "你是京房纳甲六爻研究模式的辅助解释器。只能解释服务端提供的 FACTS、RULES 和 SOURCES；不得重新排盘、改写世应、纳甲、六亲、六神、旬空或用神候选，不得在没有 selectedUseGod 的情况下替用户暗选用神，也不得把规则标签写成绝对吉凶或必然应期。",
    },
    "bazi-ziping": {
        "profile_id": "bazi-ziping-v1",
        "version": "1.0.0",
        "max_chars": 12_000,
        "system_prompt": "你是子平八字研究模式的辅助解释器。只能解释服务端提供的 FACTS、RULES 和 SOURCES；不得重新排四柱、改写藏干、十神、十二长生、五行统计、大运或流年关系，不得把标签写成唯一的身强弱、格局、用神、吉凶或应期结论。",
    },
    "ziwei": {
        "profile_id": "ziwei-doushu-v1",
        "version": "1.0.0",
        "max_chars": 12_000,
        "system_prompt": "你是紫微斗数研究模式的辅助解释器。只能解释服务端提供的 FACTS、RULES 和 SOURCES；不得重新安星、改写十二宫、主星、亮度、四化、三方四正、大限或流年，不得将结构化标签扩写为唯一的吉凶、性格、职业、婚姻或应期结论。",
    },
    "qimen": {
        "profile_id": "qimen-shijia-zhuanpan-chaibu-v1",
        "version": "1.0.0",
        "max_chars": 12_000,
        "system_prompt": "你是时家奇门转盘拆补研究模式的辅助解释器。只能解释服务端提供的 FACTS、逐步推导、RULES 和 SOURCES；不得重新起局、改写阴阳遁、局数、天地盘、九星、八门、八神、值符值使、空亡或马星，不得将结构化位置扩写为唯一吉凶、人物性格或必然应期。",
    },
    "liuren": {
        "profile_id": "liuren-shijia-jiuzong-v1",
        "version": "1.0.0",
        "max_chars": 14_000,
        "system_prompt": "你是时家大六壬四课三传研究模式的辅助解释器。只能解释服务端提供的 FACTS、逐步推导、RULES 和 SOURCES；不得重新起课、改写月将、天地盘、十二天将、四课、九宗门决策、三传或课体，不得将结构化位置和课名扩写为唯一吉凶、人物画像或必然应期。涉害评分是项目配置，需明确其版本边界。",
    },
}


def search(query: str, engine: str | None = None, limit: int = 12) -> list[dict[str, Any]]:
    words = [word.lower() for word in query.split() if word.strip()]
    stems = ENGINE_CORPUS_FILES.get(engine, (engine,)) if engine else None
    files = [CORPUS / f"{stem}.jsonl" for stem in stems if (CORPUS / f"{stem}.jsonl").exists()] if stems else CORPUS.glob("*.jsonl")
    rows = []
    for path in files:
        for line in path.read_text("utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = json.dumps(item, ensure_ascii=False).lower()
            score = sum(text.count(word) for word in words) if words else 1
            if score:
                rows.append((score, path.stem, item))
    return [{"engine": name, **item} for _, name, item in sorted(rows, key=lambda row: row[0], reverse=True)[:limit]]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _evidence_rows(engine: str, facts: Any) -> list[dict[str, Any]]:
    rows = [row for stem in ENGINE_CORPUS_FILES.get(engine, ()) for row in search("", stem, limit=1_000)]
    if engine == "zhouyi-textual" and isinstance(facts, dict):
        numbers = {
            value.get("number") for key in ("primary", "changed")
            if isinstance(value := facts.get(key), dict) and value.get("number") is not None
        }
        moving = set(facts.get("movingLines", []))
        sections = {"hexagram-name", "judgement", "tuan", "great-image"}
        rows = [
            row for row in rows
            if row.get("hexagramNumber") in numbers
            and (row.get("section") in sections or (row.get("section") in {"line", "line-image"} and row.get("line") in moving))
        ] or rows
    elif isinstance(facts, dict):
        rule_ids = {hit.get("ruleId") for hit in facts.get("ruleHits", []) if isinstance(hit, dict)}
        rows = [row for row in rows if row.get("id") in rule_ids] or rows
    return rows


def _format_evidence(row: dict[str, Any]) -> str:
    hexagram = f" hexagram={row['hexagramNumber']}" if row.get("hexagramNumber") is not None else ""
    line = f" line={row['line']}" if row.get("line") is not None else ""
    source = row.get("sourceUrl") or ""
    if source and row.get("sourcePage"):
        source += f"#{row['sourcePage']}"
    source = source or row.get("sourcePage") or "未知来源"
    return "\n".join((
        f"[{row.get('id', 'unknown-source')}]" + hexagram + f" section={row.get('section', '')}" + line,
        row.get("textTraditional") or row.get("textSimplified") or "",
        f"source={source}",
    ))


def _prompt_evidence(engine: str, facts: Any, max_chars: int) -> tuple[str, list[str]]:
    selected: list[str] = []
    source_ids: list[str] = []
    for row in _evidence_rows(engine, facts):
        formatted = _format_evidence(row)
        candidate = "\n\n".join((*selected, formatted))
        if len(candidate) <= max_chars:
            selected.append(formatted)
            if row.get("id"):
                source_ids.append(row["id"])
    return "\n\n".join(selected), source_ids


def build_grounded_prompt(question: str, engine: str, category: str, values: dict | None, facts: Any) -> dict[str, Any]:
    profile = PROMPT_PROFILES.get(engine, {
        "profile_id": "fortune-research-v1",
        "version": "1.0.0",
        "max_chars": 12_000,
        "system_prompt": "你是传统术数研究模式的辅助解释器。只能解释服务端提供的 FACTS、RULES 和 SOURCES，不得重新排盘、改写确定性字段或把推测写成事实。",
    })
    facts_record = facts if isinstance(facts, dict) else {}
    facts_json = _json({
        "engineId": engine,
        "questionCategory": category,
        "input": values or {},
        "facts": facts,
    })
    rules_json = _json(facts_record.get("ruleHits") or facts_record.get("rules") or "（本次没有单独的结构化规则命中）")
    source_text, source_ids = _prompt_evidence(engine, facts, profile["max_chars"])
    user_prompt = "\n".join((
        "<FACTS>", facts_json, "</FACTS>",
        "<RULES>", rules_json, "</RULES>",
        "<SOURCES>", source_text or "（本次没有可用来源段落）", "</SOURCES>",
        "<USER_QUESTION>", question or "未命名占测", "</USER_QUESTION>",
        "请严格依据以上 FACTS、RULES 和 SOURCES 完成一次研究模式的辅助解释；不能新增或覆盖任何确定性字段。",
    ))
    return {
        "system_prompt": profile["system_prompt"],
        "user_prompt": user_prompt,
        "source_ids": source_ids,
        "profile_id": profile["profile_id"],
        "version": profile["version"],
    }


def build_agent_prompt(question: str, engine: str, values: dict, facts: dict, category: str = "other") -> str:
    prompt = build_grounded_prompt(question, engine, category, values, facts)
    return "\n".join((
        "<SYSTEM_PROMPT>", prompt["system_prompt"], "</SYSTEM_PROMPT>",
        "<USER_PROMPT>", prompt["user_prompt"], "</USER_PROMPT>",
    ))


def interpret(question: str, facts: list[dict[str, Any]], *, engine: str | None = None,
              values: dict | None = None, category: str = "other") -> str:
    fact_payload: Any = facts[0] if len(facts) == 1 else facts
    detected_engine = engine or (fact_payload.get("engineId") if isinstance(fact_payload, dict) else None) or "zhouyi-textual"
    prompt = build_grounded_prompt(question, detected_engine, category, values, fact_payload)
    client, model = analysis.build_client(), str(analysis.llm_status()["model"])
    provider = str(analysis.llm_status()["provider"])
    if provider == "openai-responses":
        return client.responses.create(
            model=model, instructions=prompt["system_prompt"], input=prompt["user_prompt"], max_output_tokens=1800
        ).output_text
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": prompt["system_prompt"]}, {"role": "user", "content": prompt["user_prompt"]}],
        max_tokens=1800,
    )
    return response.choices[0].message.content or ""
