#!/usr/bin/env python3
"""Validate opportunity CSV files and the 30-row sample set."""

from __future__ import annotations

import csv
import sys
from pathlib import Path
from urllib.parse import urlsplit


REQUIRED_FIELDS = [
    "机会名称",
    "机会类型",
    "机会类型分组",
    "主办方",
    "议题标签",
    "主题分区",
    "相关度",
    "截止日期",
    "会议日期",
    "地点/线上",
    "原网页链接",
    "申请/投稿链接",
    "参加条件",
    "费用",
    "是否有资助",
    "资助说明链接",
    "需要准备的材料",
    "岗位类型",
    "岗位职能",
    "排除原因",
    "行动优先级",
    "状态",
    "备注",
]

CORE_TOPICS = ["发展", "不平等", "AI", "气候", "金融", "债务", "全球治理", "可持续"]
LOW_TOPICS = ["粮食安全", "人口", "公共卫生"]
OPPORTUNITY_GROUPS = {"会议", "学术论坛/CFP", "Fellowship", "Internship", "青年项目", "Policy/Summer School", "其他"}
TOPIC_SECTIONS = {"AI治理", "全球治理/国际组织", "可持续发展/气候", "发展/不平等", "国际金融/债务", "国际关系/政治学", "其他"}
EXCLUDED_INTERNSHIP_TERMS = ["城市规划", "法律", "人力资源", "IT", "财务", "采购", "行政", "医学", "工程"]


def is_url(value: str) -> bool:
    parts = urlsplit(value.strip())
    return parts.scheme in {"http", "https"} and bool(parts.netloc)


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = [field for field in REQUIRED_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            raise AssertionError("缺少字段：" + "、".join(missing))
        return [{key: (value or "").strip() for key, value in row.items()} for row in reader]


def validate(path: Path) -> None:
    rows = load_rows(path)
    if len(rows) < 40:
        raise AssertionError(f"样例数量不足 40 条，当前为 {len(rows)} 条。")

    for index, row in enumerate(rows, start=2):
        for field in REQUIRED_FIELDS:
            if field in {"岗位类型", "岗位职能", "排除原因"}:
                continue
            if not row.get(field):
                raise AssertionError(f"第 {index} 行字段为空：{field}")
        if row["机会类型分组"] not in OPPORTUNITY_GROUPS:
            raise AssertionError(f"第 {index} 行机会类型分组不合法：{row['机会类型分组']}")
        if row["主题分区"] not in TOPIC_SECTIONS:
            raise AssertionError(f"第 {index} 行主题分区不合法：{row['主题分区']}")
        if row["行动优先级"] not in {"高", "中高", "中", "低"}:
            raise AssertionError(f"第 {index} 行行动优先级不合法：{row['行动优先级']}")
        if not is_url(row["原网页链接"]):
            raise AssertionError(f"第 {index} 行原网页链接不是有效 URL：{row['原网页链接']}")
        if row["申请/投稿链接"] != "待核查" and not is_url(row["申请/投稿链接"]):
            raise AssertionError(f"第 {index} 行申请/投稿链接不是有效 URL 或待核查。")
        if row["资助说明链接"] != "待核查" and not is_url(row["资助说明链接"]):
            raise AssertionError(f"第 {index} 行资助说明链接不是有效 URL 或待核查。")

    fellowship_rows = [row for row in rows if "fellow" in (row["机会类型"] + row["机会名称"]).lower()]
    if len(fellowship_rows) < 5:
        raise AssertionError("fellowship 样例少于 5 条。")

    group_values = {row["机会类型分组"] for row in rows}
    required_groups = {"会议", "学术论坛/CFP", "Fellowship", "Internship", "青年项目"}
    missing_groups = required_groups - group_values
    if missing_groups:
        raise AssertionError("缺少机会类型分组样例：" + "、".join(sorted(missing_groups)))

    core_rows = [row for row in rows if any(topic.lower() in (row["议题标签"] + row["备注"]).lower() for topic in CORE_TOPICS)]
    if len(core_rows) < 20:
        raise AssertionError("核心议题样例少于 20 条。")

    low_rows = [row for row in rows if any(topic in row["议题标签"] for topic in LOW_TOPICS)]
    if not low_rows:
        raise AssertionError("缺少粮食安全、人口、公共卫生等低优先级边界测试样例。")
    if not any(row["相关度"] == "低" for row in low_rows):
        raise AssertionError("低优先级边界样例没有被标为低相关。")

    funded_rows = [row for row in rows if row["是否有资助"] in {"是", "待核查"}]
    if len(funded_rows) < 15:
        raise AssertionError("资助/待核查资助样例不足。")

    internship_rows = [row for row in rows if row["机会类型分组"] == "Internship"]
    if len(internship_rows) < 8:
        raise AssertionError("Internship 样例少于 8 条。")
    if any(row["岗位类型"] != "Internship" for row in internship_rows):
        raise AssertionError("存在未明确标注岗位类型为 Internship 的实习样例。")

    excluded = [row for row in internship_rows if row["排除原因"]]
    if len(excluded) < 3:
        raise AssertionError("强专业壁垒 internship 排除样例少于 3 条。")
    excluded_text = " ".join(row["排除原因"] for row in excluded)
    if not any(term in excluded_text for term in EXCLUDED_INTERNSHIP_TERMS):
        raise AssertionError("排除样例未覆盖城市规划、法律、HR、IT、财务等强专业壁垒。")
    if any(row["行动优先级"] != "低" or row["相关度"] != "低" for row in excluded):
        raise AssertionError("被排除的 internship 必须标为低相关和低优先级。")

    print(f"Validation passed: {len(rows)} opportunities checked.")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("04-模板/30条样例机会.csv")
    try:
        validate(path)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
