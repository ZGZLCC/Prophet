"""Calendar adapter matching the former TypeScript calculation policy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo

from lunar_python import Solar


STEMS = list("甲乙丙丁戊己庚辛壬癸")
BRANCHES = list("子丑寅卯辰巳午未申酉戌亥")
SOLAR_TERMS = ["小寒","大寒","立春","雨水","惊蛰","春分","清明","谷雨","立夏","小满","芒种","夏至","小暑","大暑","立秋","处暑","白露","秋分","寒露","霜降","立冬","小雪","大雪","冬至"]
_TERM_MONTH_DAY = [(1,6),(1,20),(2,4),(2,19),(3,6),(3,21),(4,5),(4,20),(5,6),(5,21),(6,6),(6,21),(7,7),(7,22),(8,7),(8,23),(9,7),(9,23),(10,8),(10,23),(11,7),(11,22),(12,7),(12,22)]


def ganzhi(index: int) -> dict:
    index %= 60
    return {"index": index, "stemNumber": index % 10 + 1, "stem": STEMS[index % 10], "branchNumber": index % 12 + 1, "branch": BRANCHES[index % 12]}


def day_ganzhi(year: int, month: int, day: int) -> dict:
    anchor = datetime(2000, 1, 7)
    return ganzhi((datetime(year, month, day) - anchor).days)


def _longitude(instant: datetime) -> float:
    origin = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)
    days = (instant - origin).total_seconds() / 86400
    mean_longitude = (280.460 + 0.9856474 * days) % 360
    anomaly = math.radians((357.528 + 0.9856003 * days) % 360)
    return (mean_longitude + 1.915 * math.sin(anomaly) + .020 * math.sin(2 * anomaly)) % 360


def solar_terms(year: int) -> list[dict]:
    result = []
    for index, (month, day) in enumerate(_TERM_MONTH_DAY):
        instant = datetime(year, month, day, tzinfo=timezone.utc)
        target = (285 + index * 15) % 360
        for _ in range(8):
            difference = ((_longitude(instant) - target + 540) % 360) - 180
            instant -= timedelta(days=difference / .9856)
        result.append({"index": index, "name": SOLAR_TERMS[index], "longitude": target, "instant": instant})
    return result


def _terms_around(instant: datetime) -> tuple[dict | None, dict | None]:
    terms = sorted(sum((solar_terms(year) for year in range(instant.year - 1, instant.year + 2)), []), key=lambda item: item["instant"])
    current = None
    for term in terms:
        if term["instant"] <= instant:
            current = term
        else:
            return current, term
    return current, None


def _month_branch(term_index: int | None) -> int:
    if term_index is None:
        return 2
    even = term_index if term_index % 2 == 0 else (term_index - 1) % 24
    return int((2 + (even - 2) / 2) % 12) + 1


def _month_ganzhi(year_stem: int, month_branch: int) -> dict:
    first = {1:3, 6:3, 2:5, 7:5, 3:7, 8:7, 4:9, 9:9, 5:1, 10:1}[year_stem]
    stem = (first - 1 + (month_branch - 3) % 12) % 10 + 1
    return next(ganzhi(index) for index in range(60) if index % 10 == stem - 1 and index % 12 == month_branch - 1)


def create_calendar(value: str | datetime, *, policy_id: str = "civil-standard-time-v1", timezone_name: str = "Asia/Shanghai") -> dict:
    instant = datetime.fromisoformat(value) if isinstance(value, str) else value
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=ZoneInfo(timezone_name))
    utc = instant.astimezone(timezone.utc)
    local = instant.astimezone(ZoneInfo(timezone_name))
    day_boundary = policy_id == "traditional-zi-chu-li-chun-v1" and local.hour >= 23
    effective = local + timedelta(days=1) if day_boundary else local
    lunar = Solar.fromYmdHms(effective.year, effective.month, effective.day, effective.hour, effective.minute, effective.second).getLunar()
    current, following = _terms_around(utc)
    year = effective.year
    if policy_id != "civil-standard-time-v1" and utc < solar_terms(effective.year)[2]["instant"]:
        year -= 1
    year_stem = (year - 4) % 10 + 1
    year_branch = (year - 4) % 12 + 1
    month_branch = _month_branch(current["index"] if current else None)
    month = _month_ganzhi(year_stem, month_branch)
    day = day_ganzhi(effective.year, effective.month, effective.day)
    hour_branch = 1 if local.hour in (23, 0) else (local.hour + 1) // 2 + 1
    def public_term(term: dict | None) -> dict | None:
        if not term:
            return None
        return {**term, "instant": term["instant"].isoformat().replace("+00:00", "Z"), "localDateTime": term["instant"].astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None).isoformat(timespec="seconds")}
    return {
        "adapterId":"lunar-python-v1", "adapterVersion":"1.4.8", "effectiveLocalDateTime":effective.replace(tzinfo=None).isoformat(timespec="seconds"),
        "gregorianYear":effective.year, "gregorianMonth":effective.month, "gregorianDay":effective.day,
        "lunar":{"calendar":"chinese-lunisolar", "year":lunar.getYear(), "month":abs(lunar.getMonth()), "day":lunar.getDay(), "isLeapMonth":lunar.getMonth() < 0, "yearName":lunar.getYearInGanZhi()},
        "yearNumber":year, "yearStemNumber":year_stem, "yearStem":STEMS[year_stem-1], "yearBranchNumber":year_branch, "yearBranch":BRANCHES[year_branch-1],
        "monthStemNumber":month["stemNumber"], "monthStem":month["stem"], "monthBranchNumber":month_branch, "monthBranch":month["branch"],
        "dayStemNumber":day["stemNumber"], "dayStem":day["stem"], "dayBranchNumber":day["branchNumber"], "dayBranch":day["branch"], "dayGanZhiIndex":day["index"],
        "hourBranchNumber":hour_branch, "hourBranch":BRANCHES[hour_branch-1], "dayBoundaryApplied":day_boundary,
        "solarTerm":{"current":public_term(current), "next":public_term(following)},
    }
