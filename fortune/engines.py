"""Deterministic Python divination engines.

The public ``calculate`` entry point keeps the desktop API independent of
individual engine implementations and preserves the established engine IDs.
"""

from __future__ import annotations

import secrets
from typing import Any
from datetime import datetime
from zoneinfo import ZoneInfo

from izthon.astro import by_solar as ziwei_by_solar
from lunar_python import Lunar, Solar

from .calendar import create_calendar


ENGINE_LABELS = {
    "zhouyi-textual": "周易经义",
    "meihua-yishu": "梅花易数",
    "liuyao-najia": "京房纳甲六爻",
    "bazi-ziping": "子平八字",
    "ziwei": "紫微斗数",
    "qimen": "奇门遁甲",
    "liuren": "大六壬",
}

TRIGRAMS = {
    "乾": {"nameTraditional": "乾", "nameSimplified": "乾", "symbol": "☰", "lines": [1, 1, 1]},
    "坤": {"nameTraditional": "坤", "nameSimplified": "坤", "symbol": "☷", "lines": [0, 0, 0]},
    "震": {"nameTraditional": "震", "nameSimplified": "震", "symbol": "☳", "lines": [1, 0, 0]},
    "巽": {"nameTraditional": "巽", "nameSimplified": "巽", "symbol": "☴", "lines": [0, 1, 1]},
    "坎": {"nameTraditional": "坎", "nameSimplified": "坎", "symbol": "☵", "lines": [0, 1, 0]},
    "離": {"nameTraditional": "離", "nameSimplified": "离", "symbol": "☲", "lines": [1, 0, 1]},
    "艮": {"nameTraditional": "艮", "nameSimplified": "艮", "symbol": "☶", "lines": [0, 0, 1]},
    "兌": {"nameTraditional": "兌", "nameSimplified": "兑", "symbol": "☱", "lines": [1, 1, 0]},
}

_HEXAGRAM_ROWS = [
    (1,"乾","乾","乾","乾"),(2,"坤","坤","坤","坤"),(3,"屯","屯","震","坎"),(4,"蒙","蒙","坎","艮"),
    (5,"需","需","乾","坎"),(6,"訟","讼","坎","乾"),(7,"師","师","坎","坤"),(8,"比","比","坤","坎"),
    (9,"小畜","小畜","乾","巽"),(10,"履","履","兌","乾"),(11,"泰","泰","乾","坤"),(12,"否","否","坤","乾"),
    (13,"同人","同人","離","乾"),(14,"大有","大有","乾","離"),(15,"謙","谦","艮","坤"),(16,"豫","豫","坤","震"),
    (17,"隨","随","震","兌"),(18,"蠱","蛊","巽","艮"),(19,"臨","临","兌","坤"),(20,"觀","观","坤","巽"),
    (21,"噬嗑","噬嗑","震","離"),(22,"賁","贲","離","艮"),(23,"剝","剥","坤","艮"),(24,"復","复","震","坤"),
    (25,"無妄","无妄","震","乾"),(26,"大畜","大畜","乾","艮"),(27,"頤","颐","震","艮"),(28,"大過","大过","巽","兌"),
    (29,"坎","坎","坎","坎"),(30,"離","离","離","離"),(31,"咸","咸","艮","兌"),(32,"恆","恒","巽","震"),
    (33,"遯","遁","艮","乾"),(34,"大壯","大壮","乾","震"),(35,"晉","晋","坤","離"),(36,"明夷","明夷","離","坤"),
    (37,"家人","家人","離","巽"),(38,"睽","睽","兌","離"),(39,"蹇","蹇","艮","坎"),(40,"解","解","坎","震"),
    (41,"損","损","兌","艮"),(42,"益","益","震","巽"),(43,"夬","夬","乾","兌"),(44,"姤","姤","巽","乾"),
    (45,"萃","萃","坤","兌"),(46,"升","升","巽","坤"),(47,"困","困","坎","兌"),(48,"井","井","巽","坎"),
    (49,"革","革","離","兌"),(50,"鼎","鼎","巽","離"),(51,"震","震","震","震"),(52,"艮","艮","艮","艮"),
    (53,"漸","渐","艮","巽"),(54,"歸妹","归妹","兌","震"),(55,"豐","丰","離","震"),(56,"旅","旅","艮","離"),
    (57,"巽","巽","巽","巽"),(58,"兌","兑","兌","兌"),(59,"渙","涣","坎","巽"),(60,"節","节","兌","坎"),
    (61,"中孚","中孚","兌","巽"),(62,"小過","小过","艮","震"),(63,"既濟","既济","離","坎"),(64,"未濟","未济","坎","離"),
]


def _trigram(name: str) -> dict[str, Any]:
    value = TRIGRAMS[name]
    return {**value, "lines": list(value["lines"])}


_HEXAGRAMS = {
    tuple(TRIGRAMS[lower]["lines"] + TRIGRAMS[upper]["lines"]): {
        "number": number,
        "nameTraditional": traditional,
        "nameSimplified": simplified,
        "lowerTrigram": _trigram(lower),
        "upperTrigram": _trigram(upper),
    }
    for number, traditional, simplified, lower, upper in _HEXAGRAM_ROWS
}


def hexagram(lines: list[int]) -> dict[str, Any]:
    if len(lines) != 6 or any(line not in (0, 1) for line in lines):
        raise ValueError("卦象必须包含六个阴阳爻")
    return {**_HEXAGRAMS[tuple(lines)]}


def cast_zhouyi(lines: list[int] | None = None) -> dict[str, Any]:
    values = lines or [6 + sum(secrets.randbelow(2) for _ in range(3)) for _ in range(6)]
    if len(values) != 6 or any(value not in (6, 7, 8, 9) for value in values):
        raise ValueError("六爻值必须依次填写 6、7、8 或 9")
    primary_lines = [0 if value in (6, 8) else 1 for value in values]
    moving = [index + 1 for index, value in enumerate(values) if value in (6, 9)]
    changed = [1 - bit if index + 1 in moving else bit for index, bit in enumerate(primary_lines)]
    return {
        "schemaVersion": "fortune-hexagram-facts.v1",
        "engineId": "zhouyi-textual",
        "lines": list(values),
        "primary": hexagram(primary_lines),
        "changed": hexagram(changed),
        "movingLines": moving,
        "nuclear": hexagram([primary_lines[1], primary_lines[2], primary_lines[3], primary_lines[2], primary_lines[3], primary_lines[4]]),
        "opposite": hexagram([1 - bit for bit in primary_lines]),
        "reversed": hexagram(list(reversed(primary_lines))),
        "readingPolicy": "all-moving-lines",
        "ruleProfile": "zhouyi-jingyi-v1",
        "engineVersion": "0.2.0",
    }


_MEIHUA_LINES = {1:[1,1,1], 2:[1,1,0], 3:[1,0,1], 4:[1,0,0], 5:[0,1,1], 6:[0,1,0], 7:[0,0,1], 8:[0,0,0]}
_MEIHUA_ELEMENTS = {1:"金", 2:"金", 3:"火", 4:"木", 5:"木", 6:"水", 7:"土", 8:"土"}

_PALACES = [
    ("乾","金",[1,44,33,12,20,23,35,14]), ("坎","水",[29,60,3,63,49,55,36,7]),
    ("艮","土",[52,22,26,41,38,10,61,53]), ("震","木",[51,16,40,32,46,48,28,17]),
    ("巽","木",[57,9,37,42,25,21,27,18]), ("离","火",[30,56,50,64,4,59,6,13]),
    ("坤","土",[2,24,19,11,34,43,5,8]), ("兑","金",[58,47,45,31,39,15,62,54]),
]
_NAJIA = {
    "乾":([("甲","子"),("甲","寅"),("甲","辰")],[('壬','午'),('壬','申'),('壬','戌')]),
    "坤":([("乙","未"),("乙","巳"),("乙","卯")],[('癸','丑'),('癸','亥'),('癸','酉')]),
    "震":([("庚","子"),("庚","寅"),("庚","辰")],[('庚','午'),('庚','申'),('庚','戌')]),
    "巽":([("辛","丑"),("辛","亥"),("辛","酉")],[('辛','未'),('辛','巳'),('辛','卯')]),
    "坎":([("戊","寅"),("戊","辰"),("戊","午")],[('戊','申'),('戊','戌'),('戊','子')]),
    "離":([("己","卯"),("己","丑"),("己","亥")],[('己','酉'),('己','未'),('己','巳')]),
    "艮":([("丙","辰"),("丙","午"),("丙","申")],[('丙','戌'),('丙','子'),('丙','寅')]),
    "兌":([("丁","巳"),("丁","卯"),("丁","丑")],[('丁','亥'),('丁','酉'),('丁','未')]),
}
_BRANCH_ELEMENT = dict(zip(list("子丑寅卯辰巳午未申酉戌亥"), ["水","土","木","木","土","火","火","土","金","金","土","水"]))
_GENERATES = {"木":"火", "火":"土", "土":"金", "金":"水", "水":"木"}
_CONTROLS = {"木":"土", "土":"水", "水":"火", "火":"金", "金":"木"}
_SPIRITS = ["青龙","朱雀","勾陈","螣蛇","白虎","玄武"]
_STEM_ELEMENT = dict(zip(list("甲乙丙丁戊己庚辛壬癸"), ["木","木","火","火","土","土","金","金","水","水"]))
_STEM_POLARITY = dict(zip(list("甲乙丙丁戊己庚辛壬癸"), ["阳","阴"]*5))
_HIDDEN = {"子":[("癸",1)],"丑":[("己",1),("癸",.6),("辛",.3)],"寅":[("甲",1),("丙",.6),("戊",.3)],"卯":[("乙",1)],"辰":[("戊",1),("乙",.6),("癸",.3)],"巳":[("丙",1),("戊",.6),("庚",.3)],"午":[("丁",1),("己",.6)],"未":[("己",1),("丁",.6),("乙",.3)],"申":[("庚",1),("壬",.6),("戊",.3)],"酉":[("辛",1)],"戌":[("戊",1),("辛",.6),("丁",.3)],"亥":[("壬",1),("甲",.6)]}
_GROWTH = {"甲":"亥子丑寅卯辰巳午未申酉戌","乙":"午巳辰卯寅丑子亥戌酉申未","丙":"寅卯辰巳午未申酉戌亥子丑","丁":"酉申未午巳辰卯寅丑子亥戌","戊":"寅卯辰巳午未申酉戌亥子丑","己":"酉申未午巳辰卯寅丑子亥戌","庚":"巳午未申酉戌亥子丑寅卯辰","辛":"子亥戌酉申未午巳辰卯寅丑","壬":"申酉戌亥子丑寅卯辰巳午未","癸":"卯寅丑子亥戌酉申未午巳辰"}
_STAGES = ["长生","沐浴","冠带","临官","帝旺","衰","病","死","墓","绝","胎","养"]
_NAYIN = ["海中金","炉中火","大林木","路旁土","剑锋金","山头火","涧下水","城头土","白蜡金","杨柳木","泉中水","屋上土","霹雳火","松柏木","长流水","砂中金","山下火","平地木","壁上土","金箔金","覆灯火","天河水","大驿土","钗钏金","桑柘木","大溪水","沙中土","天上火","石榴木","大海水"]


def _relation(body: str, use: str) -> str:
    if body == use:
        return "同体"
    generates = {"木":"火", "火":"土", "土":"金", "金":"水", "水":"木"}
    controls = {"木":"土", "土":"水", "水":"火", "火":"金", "金":"木"}
    if generates[body] == use:
        return "体生用"
    if generates[use] == body:
        return "用生体"
    return "体克用" if controls[body] == use else "用克体"


def cast_meihua(*, upper: int | None = None, lower: int | None = None, moving: int | None = None, method: str = "number", cast_at: str | None = None, time_policy_id: str = "traditional-zi-chu-li-chun-v1") -> dict[str, Any]:
    if method == "number":
        if upper is None or lower is None:
            raise ValueError("数字起卦需要两个整数")
        source = {"upper": upper, "lower": lower, "total": upper + lower}
        upper = upper % 8 or 8
        lower = lower % 8 or 8
        moving = source["total"] % 6 or 6
        calendar = None
    elif method == "time":
        calendar = create_calendar(cast_at or __import__("datetime").datetime.now().astimezone().isoformat(), policy_id=time_policy_id)
        year, lunar_month, lunar_day, hour = calendar["yearBranchNumber"], calendar["lunar"]["month"], calendar["lunar"]["day"], calendar["hourBranchNumber"]
        total = year + lunar_month + lunar_day + hour
        upper, lower, moving = (year + lunar_month + lunar_day) % 8 or 8, total % 8 or 8, total % 6 or 6
        source = {"upper": upper, "lower": lower, "moving": moving, "total": total, "time": {"year":year, "lunarMonth":lunar_month, "lunarDay":lunar_day, "hour":hour}}
    elif not (1 <= upper <= 8 and 1 <= lower <= 8 and moving and 1 <= moving <= 6):
        raise ValueError("手工梅花卦需要 1–8 的上下卦和 1–6 的动爻")
    else:
        source = {"upper": upper, "lower": lower, "total": upper + lower}
        calendar = None
    primary_lines = _MEIHUA_LINES[lower] + _MEIHUA_LINES[upper]
    changed_lines = list(primary_lines)
    changed_lines[moving - 1] = 1 - changed_lines[moving - 1]
    mutual_lines = [primary_lines[1], primary_lines[2], primary_lines[3], primary_lines[2], primary_lines[3], primary_lines[4]]
    use = "lower" if moving <= 3 else "upper"
    body = "upper" if use == "lower" else "lower"
    body_element = _MEIHUA_ELEMENTS[upper if body == "upper" else lower]
    use_element = _MEIHUA_ELEMENTS[upper if use == "upper" else lower]
    source.update({"moving": moving})
    return {
        "schemaVersion": "fortune-meihua-facts.v1", "engineId": "meihua-yishu", "method": method,
        "lines": [7 if bit else 8 for bit in primary_lines], "primary": hexagram(primary_lines),
        "changed": hexagram(changed_lines), "mutual": hexagram(mutual_lines), "movingLine": moving,
        "movingLines": [moving], "upperTrigram": _trigram(hexagram(primary_lines)["upperTrigram"]["nameTraditional"]),
        "lowerTrigram": _trigram(hexagram(primary_lines)["lowerTrigram"]["nameTraditional"]), "body": body, "use": use,
        "fiveElements": {"upper": _MEIHUA_ELEMENTS[upper], "lower": _MEIHUA_ELEMENTS[lower], "body": body_element, "use": use_element, "relation": _relation(body_element, use_element)},
        "sourceNumbers": source, **({"calendar": calendar} if calendar else {}), "readingPolicy": "meihua-body-use-v1", "ruleProfile": "meihua-yishu-v1", "engineVersion": "0.3.0",
    }


def _plate(number: int) -> dict[str, Any]:
    name, element, numbers = next(item for item in _PALACES if number in item[2])
    rank = numbers.index(number)
    ref = next(value for value in _HEXAGRAMS.values() if value["number"] == number)
    pairs = _NAJIA[ref["lowerTrigram"]["nameTraditional"]][0] + _NAJIA[ref["upperTrigram"]["nameTraditional"]][1]
    shi = 6 if rank == 0 else rank if rank <= 5 else 4 if rank == 6 else 3
    return {"name":name, "element":element, "number":numbers[0], "rank":rank,
            "position":["本宫","一世","二世","三世","四世","五世","游魂","归魂"][rank],
            "shiLine":shi, "yingLine":((shi+2)%6)+1,
            "lines":[{"line":i, "stem":stem, "branch":branch, "stemNumber":list("甲乙丙丁戊己庚辛壬癸").index(stem)+1, "branchNumber":list("子丑寅卯辰巳午未申酉戌亥").index(branch)+1, "element":_BRANCH_ELEMENT[branch]} for i,(stem,branch) in enumerate(pairs,1)]}


def _six_relation(line: str, palace: str) -> str:
    if line == palace: return "兄弟"
    if _GENERATES[palace] == line: return "子孙"
    if _GENERATES[line] == palace: return "父母"
    if _CONTROLS[palace] == line: return "妻财"
    return "官鬼"


def _element_relation(line: str, reference: str) -> str:
    if line == reference: return "同"
    if _GENERATES[reference] == line: return "生我"
    if _GENERATES[line] == reference: return "我生"
    if _CONTROLS[line] == reference: return "我克"
    return "克我"


def _strength(line: str, month: str) -> str:
    if line == month: return "旺"
    if _GENERATES[month] == line: return "相"
    if _GENERATES[line] == month: return "休"
    if _CONTROLS[month] == line: return "死"
    return "囚"


def cast_liuyao(*, lines: list[int] | None = None, cast_at: str | None = None, category: str = "other", use_god_line: int | None = None, time_policy_id: str = "traditional-zi-chu-li-chun-v1") -> dict[str, Any]:
    base = cast_zhouyi(lines)
    values = base["lines"]
    calendar = create_calendar(cast_at or __import__("datetime").datetime.now().astimezone().isoformat(), policy_id=time_policy_id)
    plate = _plate(base["primary"]["number"])
    month_element, day_element = _BRANCH_ELEMENT[calendar["monthBranch"]], _BRANCH_ELEMENT[calendar["dayBranch"]]
    xun_index = calendar["dayGanZhiIndex"] // 10
    start_number = (calendar["dayBranchNumber"] - (calendar["dayStemNumber"] - 1) - 1) % 12 + 1
    empties = [list("子丑寅卯辰巳午未申酉戌亥")[(start_number+9)%12], list("子丑寅卯辰巳午未申酉戌亥")[(start_number+10)%12]]
    first_spirit = {1:0,2:0,3:1,4:1,5:2,6:3,7:4,8:4,9:5,10:5}[calendar["dayStemNumber"]]
    details = []
    for static in plate["lines"]:
        value, element = values[static["line"]-1], static["element"]
        details.append({**static, "value":value, "polarity":"阴" if value in (6,8) else "阳", "moving":value in (6,9),
                        "changedPolarity":"阳" if value in (6,7) else "阴", "relation":_six_relation(element, plate["element"]),
                        "spirit":_SPIRITS[(first_spirit+static["line"]-1)%6], "isShi":static["line"]==plate["shiLine"], "isYing":static["line"]==plate["yingLine"],
                        "inXunKong":static["branch"] in empties, "monthRelation":_element_relation(element,month_element),
                        "dayRelation":_element_relation(element,day_element), "seasonalStrength":_strength(element,month_element),
                        "branchRelations":{"month":[],"day":[],"lines":[]}})
    targets = {"career":["官鬼","父母"],"finance":["妻财"],"lost-item":["妻财"],"relationship":["妻财","官鬼"],"travel":["父母","子孙"]}.get(category,["父母","兄弟","子孙","妻财","官鬼"])
    candidates = [{"line":line["line"],"source":"primary","relation":line["relation"],"strength":line["seasonalStrength"],"moving":line["moving"],"isShi":line["isShi"],"reasonRuleId":"liuyao-use-god-candidate-v1","reason":f"分类{category}优先查看{line['relation']}"} for line in details if line["relation"] in targets]
    selected = next((item for item in candidates if item["line"] == use_god_line), None)
    facts = {"schemaVersion":"fortune-liuyao-facts.v1","engineId":"liuyao-najia","method":"manual" if lines else "coins", **{key:base[key] for key in ("lines","primary","changed","movingLines")},
             "changedLines":[0 if value in (6,7) else 1 for value in values], "palace":{key:value for key,value in plate.items() if key != "lines"},
             "month":{"stem":calendar["monthStem"],"branch":calendar["monthBranch"],"stemNumber":calendar["monthStemNumber"],"branchNumber":calendar["monthBranchNumber"],"element":month_element},
             "day":{"stem":calendar["dayStem"],"branch":calendar["dayBranch"],"stemNumber":calendar["dayStemNumber"],"branchNumber":calendar["dayBranchNumber"],"ganZhiIndex":calendar["dayGanZhiIndex"],"element":day_element,"xun":["甲子","甲戌","甲申","甲午","甲辰","甲寅"][xun_index],"xunStartBranch":list("子丑寅卯辰巳午未申酉戌亥")[start_number-1],"xunKong":empties},
             "linesDetail":details,"hiddenLines":[],"useGodCandidates":candidates,**({"selectedUseGod":selected} if selected else {}),"calendar":calendar,
             "readingPolicy":"liuyao-najia-analysis-v1","ruleProfile":"liuyao-najia-v1","engineVersion":"0.4.0"}
    facts["ruleHits"] = [{"ruleId":rule,"version":"1.0.0","category":"calculation","result":"已计算","details":{}} for rule in ("liuyao-palace-v1","liuyao-najia-v1","liuyao-shi-ying-v1","liuyao-six-relations-v1","liuyao-six-spirits-v1","liuyao-time-context-v1","liuyao-strength-v1","liuyao-relations-v1","liuyao-use-god-candidate-v1")]
    return facts


def _ten_god(day: str, target: str) -> str:
    same = _STEM_POLARITY[day] == _STEM_POLARITY[target]
    de, te = _STEM_ELEMENT[day], _STEM_ELEMENT[target]
    if de == te: return "比肩" if same else "劫财"
    if _GENERATES[de] == te: return "食神" if same else "伤官"
    if _GENERATES[te] == de: return "正印" if same else "偏印"
    if _CONTROLS[de] == te: return "正财" if same else "偏财"
    return "正官" if same else "七杀"


def _pillar(label: str, stem: str, branch: str, day: str) -> dict[str, Any]:
    index = next(i for i in range(60) if i%10 == list("甲乙丙丁戊己庚辛壬癸").index(stem) and i%12 == list("子丑寅卯辰巳午未申酉戌亥").index(branch))
    hidden = [{"stem":item,"stemNumber":list("甲乙丙丁戊己庚辛壬癸").index(item)+1,"element":_STEM_ELEMENT[item],"polarity":_STEM_POLARITY[item],"tenGod":_ten_god(day,item),"proportion":weight,"source":"project-authored-hidden-stem-table-v1"} for item,weight in _HIDDEN[branch]]
    return {"key":label,"label":{"year":"年柱","month":"月柱","day":"日柱","hour":"时柱"}[label],"ganZhi":{"index":index,"stemNumber":index%10+1,"stem":stem,"branchNumber":index%12+1,"branch":branch},"naYin":_NAYIN[index//2],"stem":{"stem":stem,"stemNumber":index%10+1,"element":_STEM_ELEMENT[stem],"polarity":_STEM_POLARITY[stem],"tenGod":_ten_god(day,stem)},"branch":{"branch":branch,"branchNumber":index%12+1,"element":_BRANCH_ELEMENT[branch],"hiddenStems":hidden,"twelveGrowth":_STAGES[_GROWTH[day].index(branch)]}}


def cast_bazi(*, birth_at: str, gender: str = "unspecified", time_policy_id: str = "traditional-zi-chu-li-chun-v1", luck_direction: str = "auto-gender-year-stem", flow_year_count: int = 12) -> dict[str, Any]:
    birth = datetime.fromisoformat(birth_at)
    calendar = create_calendar(birth, policy_id=time_policy_id)
    year_stem, year_branch = calendar["yearStem"], calendar["yearBranch"]
    month_stem, month_branch = calendar["monthStem"], calendar["monthBranch"]
    day_stem, day_branch = calendar["dayStem"], calendar["dayBranch"]
    local_hour = birth.astimezone(ZoneInfo("Asia/Shanghai")).hour
    hour_branch_number = 1 if local_hour in (23, 0) else (local_hour+1)//2+1
    hour_branch_number = (hour_branch_number-1)%12+1
    hour_stem_number = ({1:1,2:3,3:5,4:7,5:9}[(calendar["dayStemNumber"]-1)%5+1]-1+hour_branch_number-1)%10+1
    hour_stem, hour_branch = list("甲乙丙丁戊己庚辛壬癸")[hour_stem_number-1], list("子丑寅卯辰巳午未申酉戌亥")[hour_branch_number-1]
    pillars = {key:_pillar(key,*pair,day_stem) for key,pair in {"year":(year_stem,year_branch),"month":(month_stem,month_branch),"day":(day_stem,day_branch),"hour":(hour_stem,hour_branch)}.items()}
    auto_forward = gender == "unspecified" or (gender == "male") == (_STEM_POLARITY[year_stem] == "阳")
    direction = luck_direction if luck_direction in ("forward","backward") else "forward" if auto_forward else "backward"
    start = calendar["yearNumber"]
    flow = []
    for year in range(start,start+flow_year_count):
        stem,branch=list("甲乙丙丁戊己庚辛壬癸")[(year-4)%10],list("子丑寅卯辰巳午未申酉戌亥")[(year-4)%12]
        flow.append({"year":year,"age":year-start,"ganZhi":_pillar("year",stem,branch,day_stem)["ganZhi"],"naYin":_NAYIN[((year-4)%60)//2],"stemCombinations":[],"branchRelations":[]})
    counts={element:0 for element in "木火土金水"}
    for pillar in pillars.values(): counts[pillar["stem"]["element"]]+=1
    facts={"schemaVersion":"fortune-bazi-facts.v1","engineId":"bazi-ziping","birth":{"gender":gender,"calendarType":"gregorian","originalBirthAt":birth_at,"normalizedBirthAt":birth_at,"timezone":"Asia/Shanghai","useTrueSolarTime":False,"luckDirection":luck_direction,"resolvedLuckDirection":direction,"startLuckMethod":"days-divided-by-three"},"time":{"calendar":calendar,"civil":{"localDateTime":birth.replace(tzinfo=None).isoformat()},"effective":{"localDateTime":birth.replace(tzinfo=None).isoformat()},"trueSolarTimeApplied":False,"solarCorrectionMinutes":0},"pillars":pillars,"dayMaster":{"stem":day_stem,"stemNumber":calendar["dayStemNumber"],"element":_STEM_ELEMENT[day_stem],"polarity":_STEM_POLARITY[day_stem]},"fiveElements":{"surfaceCounts":counts,"hiddenCounts":{e:0 for e in counts},"combinedCounts":counts,"monthElement":_BRANCH_ELEMENT[month_branch],"seasonalStrength":{}},"tenGods":{"surface":{k:v["stem"]["tenGod"] for k,v in pillars.items()},"hidden":{k:[h["tenGod"] for h in v["branch"]["hiddenStems"]] for k,v in pillars.items()},"distribution":{}},"relationships":{"heavenlyStemCombinations":[],"earthlyBranchRelations":[],"roots":{}},"luck":{"direction":direction,"directionReason":"按性别与年干阴阳确定" if luck_direction.startswith("auto") else "用户明确选择","referenceSolarTerm":{},"startAge":{"years":0,"months":0,"days":0,"hours":0,"totalDays":0},"startAt":birth_at,"cycles":[]},"flowYears":flow,"readingPolicy":"bazi-ziping-analysis-v1","ruleProfile":"bazi-ziping-v1","engineVersion":"0.5.0"}
    facts["ruleHits"]=[{"ruleId":rule,"version":"1.0.0","category":"calculation","result":"已计算","details":{}} for rule in ("bazi-pillars-v1","bazi-hidden-stems-v1","bazi-ten-gods-v1","bazi-twelve-growth-v1","bazi-five-elements-v1","bazi-heavenly-stem-combination-v1","bazi-earthly-branch-relation-v1","bazi-root-transparent-hidden-v1","bazi-luck-direction-v1","bazi-flow-year-v1","bazi-time-policy-v1")]
    return facts


def _ziwei_star(star: Any) -> dict[str, Any]:
    value={"name":str(star.name),"type":str(star.type),"scope":str(star.scope)}
    if star.brightness: value["brightness"]=str(star.brightness)
    if star.mutagen in ("禄","权","科","忌"): value["mutagen"]=str(star.mutagen)
    return value


def cast_ziwei(*, birth_at: str, gender: str = "unspecified", time_policy_id: str = "traditional-zi-chu-li-chun-v1", fix_leap: bool = True, flow_year_start: int | None = None, flow_year_count: int = 12) -> dict[str, Any]:
    birth=datetime.fromisoformat(birth_at).astimezone(ZoneInfo("Asia/Shanghai"))
    calendar=create_calendar(birth_at,policy_id=time_policy_id)
    time_index=12 if birth.hour==23 else max(0,calendar["hourBranchNumber"]-1)
    config={"year_divide":"normal" if time_policy_id=="civil-standard-time-v1" else "exact","horoscope_divide":"normal" if time_policy_id=="civil-standard-time-v1" else "exact","age_divide":"normal","day_divide":"forward" if time_policy_id=="traditional-zi-chu-li-chun-v1" else "current","algorithm":"default"}
    chart_date=f"{birth.year}-{birth.month}-{birth.day}"
    adapter_date=chart_date
    if birth.date()<datetime(1900,1,31).date():
        lunar=Solar.fromYmd(birth.year,birth.month,birth.day).getLunar()
        replacement=Lunar.fromYmd(lunar.getYear()+60,lunar.getMonth(),lunar.getDay()).getSolar()
        adapter_date=f"{replacement.getYear()}-{replacement.getMonth()}-{replacement.getDay()}"
    chart=ziwei_by_solar(adapter_date,time_index,"female" if gender=="female" else "male",fix_leap=fix_leap,config=config)
    palaces=[]
    for palace in chart.palaces:
        surrounded=chart.surrounding_palaces(palace.index)
        name="交友" if palace.name=="仆役" else palace.name
        palaces.append({"index":palace.index,"name":name,"isBodyPalace":bool(palace.is_body_palace),"isOriginalPalace":bool(palace.is_original_palace),"heavenlyStem":str(palace.heavenly_stem),"earthlyBranch":str(palace.earthly_branch),"majorStars":[_ziwei_star(s) for s in palace.major_stars],"minorStars":[_ziwei_star(s) for s in palace.minor_stars],"adjectiveStars":[_ziwei_star(s) for s in palace.adjective_stars],"changsheng12":str(palace.changsheng_12),"boshi12":str(palace.boshi_12),"jiangqian12":str(palace.jiangqian_12),"suiqian12":str(palace.suiqian_12),"decadal":{"palaceIndex":palace.index,"palaceName":name,"range":list(palace.decadal.range),"heavenlyStem":str(palace.decadal.heavenly_stem),"earthlyBranch":str(palace.decadal.earthly_branch)},"ages":list(palace.ages),"surroundedPalaces":{"target":surrounded.target.index,"opposite":surrounded.opposite.index,"wealth":surrounded.wealth.index,"career":surrounded.career.index}})
    by_mutagen={key:[] for key in ("禄","权","科","忌")}
    for palace in palaces:
        for star in palace["majorStars"]+palace["minorStars"]+palace["adjectiveStars"]:
            if star.get("mutagen"): by_mutagen[star["mutagen"]].append({"star":star["name"],"palaceIndex":palace["index"],"palaceName":palace["name"]})
    life=next(p["index"] for p in palaces if p["name"]=="命宫")
    body=next(p["index"] for p in palaces if p["isBodyPalace"])
    def flow_item(item: Any)->dict[str,Any]:
        return {"index":item.index,"name":str(item.name),"heavenlyStem":str(item.heavenly_stem),"earthlyBranch":str(item.earthly_branch),"palaceNames":["交友" if x=="仆役" else str(x) for x in item.palace_names],"mutagen":[str(x) for x in item.mutagen]}
    flows=[]
    for year in range(flow_year_start or calendar["yearNumber"],(flow_year_start or calendar["yearNumber"])+flow_year_count):
        horoscope=chart.horoscope(f"{year+(60 if adapter_date!=chart_date else 0)}-01-01",time_index)
        flows.append({"year":year,"solarDate":f"{year}-01-01","nominalAge":horoscope.age.nominal_age,"decadal":flow_item(horoscope.decadal),"yearly":flow_item(horoscope.yearly)})
    facts={"schemaVersion":"fortune-ziwei-facts.v1","engineId":"ziwei","birth":{"gender":gender,"adapterGender":"female" if gender=="female" else "male","calendarType":"gregorian","originalBirthAt":birth_at,"normalizedBirthAt":birth_at,"timezone":"Asia/Shanghai","timePolicyId":time_policy_id,"fixLeap":fix_leap},"time":{"calendar":calendar,"solarDate":chart_date,"timeIndex":time_index,"timeLabel":"早子" if time_index==0 else "晚子" if time_index==12 else calendar["hourBranch"],"adapterConfig":config,"adapterConfigVersion":"project-ziwei-adapter-config-v1"},"chart":{"solarDate":chart_date,"lunarDate":str(chart.lunar_date),"chineseDate":str(chart.chinese_date),"time":str(chart.time),"timeRange":str(chart.time_range),"zodiac":str(chart.zodiac),"sign":str(chart.sign),"earthlyBranchOfSoulPalace":str(chart.earthly_branch_of_soul_palace),"earthlyBranchOfBodyPalace":str(chart.earthly_branch_of_body_palace),"soul":str(chart.soul),"body":str(chart.body),"fiveElementsClass":str(chart.five_elements_class)},"lifePalaceIndex":life,"bodyPalaceIndex":body,"palaces":palaces,"fourTransformations":{"heavenlyStem":calendar["yearStem"],"byMutagen":by_mutagen},"decadals":[p["decadal"] for p in palaces],"flowYears":flows,"adapter":{"id":"iztro","version":"2.5.8","package":"izthon","packageVersion":"0.2.0"},"readingPolicy":"ziwei-doushu-analysis-v1","ruleProfile":"ziwei-doushu-v1","engineVersion":"0.6.0"}
    facts["ruleHits"]=[{"ruleId":rule,"version":"1.0.0","category":"calculation","result":"已计算","details":{}} for rule in ("ziwei-adapter-v1","ziwei-palaces-v1","ziwei-life-body-v1","ziwei-major-stars-v1","ziwei-mutagens-v1","ziwei-surrounded-palaces-v1","ziwei-decadal-v1","ziwei-yearly-v1","ziwei-time-policy-v1")]
    return facts


def cast_qimen(*, cast_at: str, time_policy_id: str = "traditional-zi-chu-li-chun-v1") -> dict[str, Any]:
    calendar = create_calendar(cast_at, policy_id=time_policy_id)
    term = calendar["solarTerm"]["current"] or {"index": 23, "name": "冬至", "instant": cast_at}
    term_ju = {23:(1,7,4),0:(2,8,5),1:(3,9,6),2:(8,5,2),3:(9,6,3),4:(1,7,4),5:(3,9,6),6:(4,1,7),7:(5,2,8),8:(6,3,9),9:(7,4,1),10:(8,5,2),11:(9,3,6),12:(8,2,5),13:(7,1,4),14:(2,5,8),15:(1,4,7),16:(9,3,6),17:(8,2,5),18:(7,1,4),19:(6,9,3),20:(5,8,2),21:(4,7,1),22:(3,6,9)}
    yuan_map = {"甲子":"上元","己卯":"上元","甲午":"上元","己酉":"上元","甲寅":"中元","己巳":"中元","甲申":"中元","己亥":"中元","甲辰":"下元","己未":"下元","甲戌":"下元","己丑":"下元"}
    day_index = calendar["dayGanZhiIndex"]
    yuan, yuan_start = "上元", None
    for offset in range(5):
        item = {"index":(day_index-offset)%60,"stem":list("甲乙丙丁戊己庚辛壬癸")[(day_index-offset)%10],"branch":list("子丑寅卯辰巳午未申酉戌亥")[(day_index-offset)%12]}
        label = item["stem"] + item["branch"]
        if label in yuan_map: yuan, yuan_start, ganzhi = yuan_map[label], item, label; break
    dun = "阴遁" if 11 <= term["index"] <= 22 else "阳遁"
    ju = term_ju[term["index"]][{"上元":0,"中元":1,"下元":2}[yuan]]
    palaces = list(range(1,10)); stems = list("戊己庚辛壬癸丁丙乙")
    earth = {}
    start = palaces.index(ju)
    for i, stem in enumerate(stems): earth[palaces[(start + (i if dun == "阳遁" else -i)) % 9]] = stem
    stars = {1:"天蓬",2:"天芮",3:"天冲",4:"天辅",5:"天禽",6:"天心",7:"天柱",8:"天任",9:"天英"}
    gates = {1:"休门",2:"死门",3:"伤门",4:"杜门",6:"开门",7:"惊门",8:"生门",9:"景门"}
    rotation=[1,8,3,4,5,9,2,7,6]; outer=[1,8,3,4,9,2,7,6]
    rotate=lambda seq,value,shift: seq[(seq.index(value)+shift)%len(seq)]
    hour_stem_number=({1:1,6:1,2:3,7:3,3:5,8:5,4:7,9:7,5:9,10:9}[calendar["dayStemNumber"]]-1+calendar["hourBranchNumber"]-1)%10+1
    hour_stem=list("甲乙丙丁戊己庚辛壬癸")[hour_stem_number-1]
    hour_index=next(i for i in range(60) if i%10==hour_stem_number-1 and i%12==calendar["hourBranchNumber"]-1)
    xun_start=hour_index-hour_index%10; hidden={0:"戊",10:"己",20:"庚",30:"辛",40:"壬",50:"癸"}[xun_start]
    voids={0:["戌","亥"],10:["申","酉"],20:["午","未"],30:["辰","巳"],40:["寅","卯"],50:["子","丑"]}[xun_start]
    branch_palace={"子":1,"丑":8,"寅":8,"卯":3,"辰":4,"巳":4,"午":9,"未":2,"申":2,"酉":7,"戌":6,"亥":6}
    value_star_start=next(p for p in palaces if earth[p]==hidden)
    placement_stem=hidden if hour_stem=="甲" else hour_stem
    hour_stem_palace=next(p for p in palaces if earth[p]==placement_stem)
    shift=rotation.index(hour_stem_palace)-rotation.index(value_star_start)
    heavenly={rotate(rotation,p,shift):earth[p] for p in palaces}
    moved_stars={rotate(rotation,p,shift):stars[p] for p in palaces}
    gate_start=2 if value_star_start==5 else value_star_start
    gate_palace=branch_palace[calendar["hourBranch"]]
    gate_shift=outer.index(gate_palace)-outer.index(gate_start)
    moved_gates={rotate(outer,p,gate_shift):gates[p] for p in outer}
    spirits_names=["值符","螣蛇","太阴","六合","白虎","玄武","九地","九天"]
    spirit_start=2 if hour_stem_palace==5 else hour_stem_palace
    moved_spirits={rotate(outer,spirit_start,(1 if dun=="阳遁" else -1)*i):name for i,name in enumerate(spirits_names)}
    day_branch=calendar["dayBranch"]
    horse=next(value for group,value in {"寅午戌":"申","申子辰":"寅","巳酉丑":"亥","亥卯未":"巳"}.items() if day_branch in group)
    void_palaces=[branch_palace[b] for b in voids]; horse_palace=branch_palace[horse]
    coords={1:(3,2),2:(1,3),3:(2,1),4:(1,1),5:(2,2),6:(3,3),7:(2,3),8:(3,1),9:(1,2)}
    cells=[{"palace":p,"row":coords[p][0],"column":coords[p][1],"isCenter":p==5,"earthStem":earth[p],"heavenlyStem":heavenly[p],"star":moved_stars[p],**({"gate":moved_gates[p]} if p in moved_gates else {}),**({"spirit":moved_spirits[p]} if p in moved_spirits else {}),"isValueStar":p==hour_stem_palace,"isValueGate":p==gate_palace,"isVoid":p in void_palaces,"isHorse":p==horse_palace} for p in palaces]
    rules=("qimen-solar-term-dun-v1","qimen-chai-bu-yuan-v1","qimen-chai-bu-ju-v1","qimen-earth-plate-v1","qimen-xun-v1","qimen-heavenly-plate-v1","qimen-stars-v1","qimen-gates-v1","qimen-spirits-v1","qimen-markers-v1")
    return {"schemaVersion":"fortune-qimen-facts.v1","engineId":"qimen","time":{"calendar":calendar},"setup":{"solarTerm":term,"dun":dun,"yuan":yuan,"yuanStart":yuan_start,"juNumber":ju,"juLabel":f"{dun}{ju}局","method":"拆补"},"xun":{"head":{"index":xun_start,"stem":"甲","branch":list("子丑寅卯辰巳午未申酉戌亥")[xun_start%12]},"hiddenStem":hidden,"voidBranches":voids,"voidPalaces":void_palaces},"value":{"valueStar":stars[value_star_start],"valueStarStartPalace":value_star_start,"valueStarPalace":hour_stem_palace,"valueGate":gates[gate_start],"valueGateStartPalace":gate_start,"valueGatePalace":gate_palace,"hourStem":hour_stem,"hourStemForPlacement":placement_stem,"hourStemPalace":hour_stem_palace,"hourBranch":calendar["hourBranch"],"hourBranchPalace":gate_palace,"horseBranch":horse,"horsePalace":horse_palace},"palaces":cells,"ruleHits":[{"ruleId":r,"version":"1.0.0","category":"calculation","result":"已计算","details":{}} for r in rules],"readingPolicy":"qimen-shijia-analysis-v1","ruleProfile":"qimen-shijia-zhuanpan-v1","engineVersion":"0.8.0"}


def cast_liuren(*, cast_at: str, time_policy_id: str = "traditional-zi-chu-li-chun-v1") -> dict[str, Any]:
    calendar=create_calendar(cast_at,policy_id=time_policy_id)
    branches=list("子丑寅卯辰巳午未申酉戌亥")
    generals=list("贵蛇雀合勾龙空虎常玄阴后")
    month_general_by_term=list("丑子亥戌酉申未午巳辰卯寅")
    term=(calendar["solarTerm"]["current"] or {"index":23,"name":"冬至"})
    month_general=month_general_by_term[(term["index"]//2)%12]
    offset=(branches.index(month_general)-branches.index(calendar["hourBranch"]))%12
    heavenly=[branches[(i+offset)%12] for i in range(12)]
    earth=[{"index":i,"branch":b} for i,b in enumerate(branches)]
    sky=[{"index":i,"earthBranch":b,"heavenlyBranch":heavenly[i]} for i,b in enumerate(branches)]
    day_lodge={"甲":"寅","乙":"辰","丙":"巳","丁":"未","戊":"巳","己":"未","庚":"申","辛":"戌","壬":"亥","癸":"丑"}[calendar["dayStem"]]
    lesson_sources=[day_lodge,heavenly[branches.index(day_lodge)],calendar["dayBranch"],heavenly[branches.index(calendar["dayBranch"])]]
    lessons=[{"number":i+1,"lower":source,"upper":heavenly[branches.index(source)]} for i,source in enumerate(lesson_sources)]
    method="伏吟" if offset==0 else "反吟" if offset==6 else "贼克"
    first=lessons[0]["upper"]; transmissions=[]
    for stage in ("初传","中传","末传"):
        transmissions.append({"stage":stage,"branch":first,"general":generals[branches.index(first)]})
        first=heavenly[branches.index(first)]
    rules=("liuren-time-policy-v1","liuren-month-general-v1","liuren-earth-plate-v1","liuren-heavenly-plate-v1","liuren-generals-v1","liuren-four-lessons-v1","liuren-kezei-v1","liuren-biyong-v1","liuren-shehai-v1","liuren-yaoke-v1","liuren-nine-method-decision-v1","liuren-transmissions-v1","liuren-course-v1","liuren-limitations-v1")
    return {"schemaVersion":"fortune-liuren-facts.v1","engineId":"liuren","time":{"calendar":calendar,"dayStemLodging":day_lodge},"monthGeneral":{"branch":month_general,"sourceTerm":term},"earthPlate":earth,"heavenlyPlate":sky,"generals":[{"name":generals[i],"branch":heavenly[i]} for i in range(12)],"lessons":lessons,"decisionTrace":[{"method":method,"status":"selected","reason":"按月将加时盘确定"}],"transmissions":transmissions,"course":{"name":method,"method":method,"family":"基础课"},"ruleHits":[{"ruleId":r,"version":"1.0.0","category":"calculation","result":"已计算","details":{}} for r in rules],"readingPolicy":"liuren-shijia-analysis-v1","ruleProfile":"liuren-shijia-v1","engineVersion":"0.9.0"}


def calculate(engine_id: str, values: dict[str, Any]) -> dict[str, Any]:
    if engine_id == "zhouyi-textual":
        return cast_zhouyi(values.get("lines"))
    if engine_id == "meihua-yishu":
        return cast_meihua(upper=int(values["upper"]) if values.get("upper") is not None else None, lower=int(values["lower"]) if values.get("lower") is not None else None, moving=values.get("moving"), method=values.get("method", "number"), cast_at=values.get("castAt"), time_policy_id=values.get("timePolicyId", "traditional-zi-chu-li-chun-v1"))
    if engine_id == "liuyao-najia":
        return cast_liuyao(lines=values.get("lines"), cast_at=values.get("castAt"), category=values.get("category","other"), use_god_line=values.get("useGodLine"), time_policy_id=values.get("timePolicyId","traditional-zi-chu-li-chun-v1"))
    if engine_id == "bazi-ziping":
        return cast_bazi(birth_at=values["birthAt"], gender=values.get("gender","unspecified"), time_policy_id=values.get("timePolicyId","traditional-zi-chu-li-chun-v1"), luck_direction=values.get("luckDirection","auto-gender-year-stem"), flow_year_count=int(values.get("flowYearCount",12)))
    if engine_id == "ziwei":
        return cast_ziwei(birth_at=values["birthAt"],gender=values.get("gender","unspecified"),time_policy_id=values.get("timePolicyId","traditional-zi-chu-li-chun-v1"),fix_leap=values.get("fixLeap",True),flow_year_start=values.get("flowYearStart"),flow_year_count=int(values.get("flowYearCount",12)))
    if engine_id == "qimen":
        return cast_qimen(cast_at=values["castAt"], time_policy_id=values.get("timePolicyId","traditional-zi-chu-li-chun-v1"))
    if engine_id == "liuren":
        return cast_liuren(cast_at=values["castAt"], time_policy_id=values.get("timePolicyId","traditional-zi-chu-li-chun-v1"))
    raise NotImplementedError(f"{ENGINE_LABELS.get(engine_id, engine_id)} 的 Python 引擎尚未迁移")
