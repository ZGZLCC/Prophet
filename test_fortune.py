"""Small parity checks for the Python fortune engines."""

import json
from pathlib import Path

from fortune.engines import cast_bazi, cast_liuyao, cast_meihua, cast_zhouyi, cast_ziwei
from fortune_app import normalize_datetime


ROOT = Path(__file__).resolve().parent


def run() -> None:
    assert normalize_datetime(
        "2020-09-20T12:00", "测试时间", time_zone="America/New_York"
    ) == "2020-09-21T00:00:00+08:00"
    golden = json.loads((ROOT / "tests/fortune_fixtures/v0.1-facts-golden.json").read_text("utf-8"))
    facts = cast_zhouyi(golden["inputLines"])
    for key in ("lines", "primary", "changed", "movingLines", "nuclear", "opposite", "reversed", "readingPolicy", "ruleProfile", "engineVersion"):
        assert facts[key] == golden["facts"][key], key

    cases = json.loads((ROOT / "tests/fortune_fixtures/meihua-golden.json").read_text("utf-8"))
    for case in cases:
        source = case["input"]
        result = cast_meihua(
            upper=source.get("upperNumber", source.get("upperTrigram")),
            lower=source.get("lowerNumber", source.get("lowerTrigram")),
            moving=source.get("movingLine"), method=source["method"], cast_at=source.get("castAt"),
            time_policy_id=source.get("timePolicyId", "traditional-zi-chu-li-chun-v1"),
        )
        assert result["primary"]["number"] == case["primary"], case["id"]
        assert result["changed"]["number"] == case["changed"], case["id"]
        assert result["mutual"]["number"] == case["mutual"], case["id"]
        assert result["fiveElements"]["relation"] == case["relation"], case["id"]

    cases = json.loads((ROOT / "tests/fortune_fixtures/liuyao-golden.json").read_text("utf-8"))
    for case in cases:
        result = cast_liuyao(lines=case["lines"], cast_at="2026-08-23T12:00:00+08:00")
        assert result["primary"]["number"] == case["primary"], case["id"]
        assert result["changed"]["number"] == case["changed"], case["id"]
        assert result["movingLines"] == case["movingLines"], case["id"]

    policies = ["traditional-zi-chu-li-chun-v1", "traditional-zi-zheng-li-chun-v1", "civil-standard-time-v1"]
    cases = json.loads((ROOT / "tests/fortune_fixtures/bazi-golden.json").read_text("utf-8"))
    for case in cases:
        result = cast_bazi(birth_at=case["birthAt"], time_policy_id=policies[case["policy"]], flow_year_count=1)
        summary = "/".join(item["ganZhi"]["stem"] + item["ganZhi"]["branch"] for item in result["pillars"].values())
        assert summary == case["expected"], case["birthAt"]
        assert result["dayMaster"]["stem"] == case["dayMaster"], case["birthAt"]

    cases = json.loads((ROOT / "tests/fortune_fixtures/ziwei-golden.json").read_text("utf-8"))["cases"]
    for case in cases:
        source = case["input"]
        result = cast_ziwei(birth_at=source["birthAt"], gender=source["gender"], time_policy_id=source["timePolicyId"], flow_year_start=source["flowYearStart"], flow_year_count=1)
        expected = case["expected"]
        assert result["time"]["timeIndex"] == expected["timeIndex"], source["birthAt"]
        assert result["lifePalaceIndex"] == expected["lifePalaceIndex"], source["birthAt"]
        assert result["bodyPalaceIndex"] == expected["bodyPalaceIndex"], source["birthAt"]
        assert result["chart"]["fiveElementsClass"] == expected["fiveElementsClass"], source["birthAt"]

    print("fortune engine parity checks passed")


if __name__ == "__main__":
    run()
