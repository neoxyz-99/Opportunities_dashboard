#!/usr/bin/env python3
"""Collect opportunities, update the CSV database, and write HTML alerts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


PROJECT_DIR = Path(__file__).resolve().parents[1]
CN_TZ = timezone(timedelta(hours=8))
DB_PATH = PROJECT_DIR / "04-数据库" / "机会数据库.csv"
NOTIFIED_PATH = PROJECT_DIR / "05-历史记录" / "已提醒链接.csv"
OUTPUT_DIR = PROJECT_DIR / "06-邮件输出"
API_ENV_PATH = PROJECT_DIR / "07-配置" / "api.env"
DOCS_DIR = PROJECT_DIR / "docs"

FIELDS = [
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
    "发现日期",
    "最近核查日期",
    "链接指纹",
]

CORE_KEYWORDS = [
    "sustainable development",
    "可持续发展",
    "development",
    "发展",
    "inequality",
    "不平等",
    "ai governance",
    "人工智能治理",
    "digital governance",
    "climate",
    "气候",
    "finance",
    "金融",
    "debt",
    "债务",
    "global governance",
    "全球治理",
    "multilateral",
    "多边",
    "international organization",
    "国际组织",
]

FELLOWSHIP_KEYWORDS = [
    "fellowship",
    "fellow",
    "young professional",
    "policy fellow",
    "visiting fellow",
    "early career",
    "scholarship",
    "grant",
    "资助",
    "奖学金",
    "青年学者",
]

LOW_PRIORITY_KEYWORDS = [
    "food security",
    "粮食安全",
    "population",
    "人口",
    "public health",
    "公共卫生",
    "agriculture",
    "农业",
    "medical",
    "医学",
]

PERSONAL_FOCUS = {
    "发展": ["development", "发展", "development finance", "发展融资"],
    "不平等": ["inequality", "不平等", "inclusive growth", "包容性"],
    "AI治理": ["ai governance", "人工智能治理", "digital governance", "数字治理", "technology governance"],
    "气候治理": ["climate", "气候", "climate finance", "能源转型"],
    "金融债务": ["finance", "金融", "debt", "债务", "imf", "world bank", "treasury"],
    "全球治理": ["global governance", "全球治理", "multilateral", "多边", "international organization", "国际组织", "united nations"],
}

OPPORTUNITY_GROUPS = [
    "会议",
    "学术论坛/CFP",
    "Fellowship",
    "Internship",
    "青年项目",
    "Policy/Summer School",
    "其他",
]

TOPIC_SECTIONS = [
    "AI治理",
    "全球治理/国际组织",
    "可持续发展/气候",
    "发展/不平等",
    "国际金融/债务",
    "国际关系/政治学",
    "其他",
]

INTERNSHIP_SOURCES = [
    "UN Careers",
    "UNDP",
    "UNESCO",
    "UNIDO",
    "UNEP",
    "UNCTAD",
    "UN-Habitat",
    "OECD",
    "World Bank",
    "ADB",
]

INTERNSHIP_EXCLUSION_TERMS = [
    "urban planning",
    "城市规划",
    "legal",
    "law",
    "法律",
    "human resources",
    "hr",
    "人力资源",
    "it",
    "software",
    "data engineer",
    "developer",
    "computer",
    "计算机",
    "财务",
    "finance assistant",
    "accounting",
    "会计",
    "procurement",
    "采购",
    "administration",
    "行政",
    "medical",
    "医学",
    "engineering",
    "工程",
]

INTERNSHIP_PREFERRED_TERMS = [
    "policy",
    "research",
    "programme",
    "program",
    "partnership",
    "communications",
    "advocacy",
    "governance",
    "sustainable development",
    "climate",
    "digital",
    "ai",
    "development finance",
    "strategy",
    "政策",
    "研究",
    "项目",
    "伙伴关系",
    "传播",
    "倡导",
    "治理",
    "可持续发展",
    "气候",
    "数字",
    "战略",
]

POLITICAL_RISK_TERMS = [
    "national endowment for democracy",
    "ned",
    "freedom house",
    "human rights watch",
    "amnesty",
    "sanctions",
    "制裁",
    "china threat",
    "decoupling",
    "democracy promotion",
    "authoritarian influence",
    "taiwan strait security",
    "xinjiang",
    "uyghur",
    "tibet",
    "regime change",
    "security alliance",
    "defense policy",
    "military",
    "国家安全",
    "军事",
    "人权倡议",
]


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_text(relative_path: str) -> str:
    return (PROJECT_DIR / relative_path).read_text(encoding="utf-8")


def normalize_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parts = urlsplit(url)
    clean = parts._replace(fragment="")
    return urlunsplit(clean).rstrip("/")


def fingerprint_for(row: dict[str, str]) -> str:
    original = normalize_url(row.get("原网页链接", ""))
    apply_url = normalize_url(row.get("申请/投稿链接", ""))
    identity = original or apply_url or f"{row.get('主办方', '')}|{row.get('机会名称', '')}"
    return hashlib.sha256(identity.lower().encode("utf-8")).hexdigest()[:16]


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def load_csv(path: Path, fieldnames: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {field: (raw.get(field, "") or "").strip() for field in fieldnames}
            if row.get("机会名称") or row.get("原网页链接"):
                rows.append(row)
        return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def append_notified(rows: list[dict[str, str]], mode: str, today: str) -> None:
    NOTIFIED_PATH.parent.mkdir(parents=True, exist_ok=True)
    exists = NOTIFIED_PATH.exists()
    with NOTIFIED_PATH.open("a", encoding="utf-8", newline="") as file:
        fieldnames = ["提醒日期", "提醒类型", "机会名称", "原网页链接", "链接指纹", "备注"]
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        if not exists or NOTIFIED_PATH.stat().st_size == 0:
            writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "提醒日期": today,
                    "提醒类型": mode,
                    "机会名称": row.get("机会名称", ""),
                    "原网页链接": row.get("原网页链接", ""),
                    "链接指纹": row.get("链接指纹", ""),
                    "备注": row.get("备注", ""),
                }
            )


def load_notified_fingerprints() -> set[str]:
    rows = load_csv(NOTIFIED_PATH, ["提醒日期", "提醒类型", "机会名称", "原网页链接", "链接指纹", "备注"])
    return {row.get("链接指纹", "") for row in rows if row.get("链接指纹", "")}


def infer_relatedness(row: dict[str, str]) -> str:
    text = " ".join(str(value).lower() for value in row.values())
    core_hits = sum(1 for keyword in CORE_KEYWORDS if keyword.lower() in text)
    fellowship_hits = sum(1 for keyword in FELLOWSHIP_KEYWORDS if keyword.lower() in text)
    low_hits = sum(1 for keyword in LOW_PRIORITY_KEYWORDS if keyword.lower() in text)

    if low_hits and core_hits == 0:
        return "低"
    if core_hits >= 2 or (core_hits >= 1 and fellowship_hits >= 1):
        return "高"
    if core_hits >= 1 or fellowship_hits >= 1:
        return "中"
    return "低"


def infer_opportunity_group(row: dict[str, str]) -> str:
    text = (row.get("机会类型", "") + " " + row.get("机会名称", "") + " " + row.get("备注", "")).lower()
    if "internship" in text or "实习" in text:
        return "Internship"
    if "fellow" in text or "fellowship" in text:
        return "Fellowship"
    if "cfp" in text or "call for papers" in text or "投稿" in text or "学术年会" in text or "conference" in text and "academic" in text:
        return "学术论坛/CFP"
    if "youth" in text or "青年" in text:
        return "青年项目"
    if "policy school" in text or "summer school" in text or "winter school" in text or "training" in text:
        return "Policy/Summer School"
    if "annual meeting" in text or "forum" in text or "summit" in text or "会议" in text or "论坛" in text:
        return "会议"
    return "其他"


def infer_topic_section(row: dict[str, str]) -> str:
    text = combined_text(row)
    if any(term in text for term in ["ai", "artificial intelligence", "人工智能", "digital governance", "数字治理", "technology governance"]):
        return "AI治理"
    if any(term in text for term in ["world bank", "imf", "united nations", "oecd", "undp", "unesco", "unep", "unctad", "global governance", "multilateral", "国际组织", "联合国", "全球治理", "多边"]):
        return "全球治理/国际组织"
    if any(term in text for term in ["sustainable", "climate", "energy transition", "可持续", "气候", "能源转型"]):
        return "可持续发展/气候"
    if any(term in text for term in ["development", "inequality", "inclusive", "发展", "不平等", "包容性"]):
        return "发展/不平等"
    if any(term in text for term in ["finance", "debt", "treasury", "金融", "债务", "发展融资"]):
        return "国际金融/债务"
    if any(term in text for term in ["international relations", "political science", "politics", "国际关系", "政治学"]):
        return "国际关系/政治学"
    return "其他"


def infer_job_type(row: dict[str, str]) -> str:
    text = (row.get("机会类型", "") + " " + row.get("机会名称", "")).lower()
    if "internship" in text or "实习" in text:
        return "Internship"
    return row.get("岗位类型", "")


def infer_job_function(row: dict[str, str]) -> str:
    if row.get("岗位职能"):
        return row["岗位职能"]
    text = combined_text(row)
    if any(term in text for term in ["policy", "政策"]):
        return "政策研究"
    if any(term in text for term in ["research", "研究"]):
        return "研究支持"
    if any(term in text for term in ["communications", "advocacy", "传播", "倡导"]):
        return "传播倡导"
    if any(term in text for term in ["partnership", "伙伴关系"]):
        return "伙伴关系"
    if any(term in text for term in ["programme", "program", "项目"]):
        return "项目支持"
    if any(term in text for term in ["strategy", "战略"]):
        return "战略支持"
    return "待核查"


def internship_exclusion_reason(row: dict[str, str]) -> str:
    if infer_opportunity_group(row) != "Internship":
        return row.get("排除原因", "")
    text = combined_text(row)
    if "internship" not in text and "实习" not in text:
        return "未明确标注为 Internship"
    for term in INTERNSHIP_EXCLUSION_TERMS:
        if term in text:
            return f"岗位职能偏强专业壁垒：{term}"
    if not any(term in text for term in INTERNSHIP_PREFERRED_TERMS):
        return "未体现政策研究、项目支持、治理、可持续发展或传播倡导等优先方向"
    return row.get("排除原因", "")


def political_risk_reason(row: dict[str, str]) -> str:
    text = combined_text(row)
    for term in POLITICAL_RISK_TERMS:
        if term in text:
            return f"政治风险偏高或对中国议题框架较敏感：{term}"
    return ""


def exclusion_reason(row: dict[str, str]) -> str:
    internship_reason = internship_exclusion_reason(row)
    if internship_reason:
        return internship_reason
    return political_risk_reason(row)


def infer_action_priority(row: dict[str, str]) -> str:
    if row.get("排除原因"):
        return "低"
    if row.get("相关度") == "高" and has_clear_deadline(row):
        return "高"
    if row.get("相关度") == "高" or row.get("机会类型分组") in {"Fellowship", "Internship"}:
        return "中高"
    if row.get("相关度") == "中":
        return "中"
    return "低"


def normalize_row(raw: dict, today: str) -> dict[str, str]:
    row = {field: str(raw.get(field, "") or "").strip() for field in FIELDS}
    row["原网页链接"] = normalize_url(row.get("原网页链接", ""))
    row["申请/投稿链接"] = normalize_url(row.get("申请/投稿链接", ""))
    row["资助说明链接"] = normalize_url(row.get("资助说明链接", ""))
    row["发现日期"] = row.get("发现日期") or today
    row["最近核查日期"] = today
    row["机会类型分组"] = row.get("机会类型分组") if row.get("机会类型分组") in OPPORTUNITY_GROUPS else infer_opportunity_group(row)
    row["主题分区"] = row.get("主题分区") if row.get("主题分区") in TOPIC_SECTIONS else infer_topic_section(row)
    row["岗位类型"] = row.get("岗位类型") or infer_job_type(row)
    row["岗位职能"] = row.get("岗位职能") or infer_job_function(row)
    row["排除原因"] = row.get("排除原因") or exclusion_reason(row)
    row["相关度"] = row.get("相关度") or infer_relatedness(row)
    if row["排除原因"]:
        row["相关度"] = "低"
    row["行动优先级"] = row.get("行动优先级") or infer_action_priority(row)
    row["状态"] = row.get("状态") or "新发现"
    row["链接指纹"] = row.get("链接指纹") or fingerprint_for(row)
    return row


def merge_rows(existing: list[dict[str, str]], incoming: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    by_fingerprint = {row.get("链接指纹", ""): row for row in existing if row.get("链接指纹")}
    new_rows: list[dict[str, str]] = []

    for row in incoming:
        fingerprint = row.get("链接指纹", "")
        if fingerprint in by_fingerprint:
            current = by_fingerprint[fingerprint]
            for field in FIELDS:
                if field in {"发现日期", "链接指纹"}:
                    continue
                if row.get(field) and row.get(field) != "待核查":
                    current[field] = row[field]
        else:
            by_fingerprint[fingerprint] = row
            new_rows.append(row)

    merged = list(by_fingerprint.values())
    merged.sort(key=lambda item: (item.get("截止日期", "9999-99-99"), item.get("机会名称", "")))
    return merged, new_rows


def build_prompt(today: str, mode: str, existing_rows: list[dict[str, str]]) -> str:
    rules = read_text("00-自动化/自动任务提示词.md")
    sources = read_text("01-项目管理/固定监测源.md")
    topic_rules = read_text("01-项目管理/议题筛选规则.md")
    existing_links = "\n".join(sorted({row.get("原网页链接", "") for row in existing_rows if row.get("原网页链接")}))
    existing_links = existing_links or "暂无已入库链接。"

    return f"""
今天日期：{today}
运行模式：{mode}

请执行一次国际会议与学术机会雷达的信息监测，尤其注意：
- fellowship / policy fellowship / visiting fellowship / early-career fellowship
- internship，重点来源包括 UN Careers、UNDP、UNESCO、UNIDO、UNEP、UNCTAD、UN-Habitat、OECD、World Bank、ADB 等国际组织官网
- NGO / think tank / policy institute opportunities, especially development, climate, sustainability, global governance, international finance, debt, AI governance, and multilateral cooperation.

Internship 专项检索要求：
- 必须单独检索 UN Careers / careers.un.org 的 internship，不要用 World Bank 或 OECD internship 代替 UN internship。
- 优先查询这些方向：political affairs internship, public information internship, sustainable development internship, economic affairs internship, programme management internship, communications internship, partnerships internship, governance internship, digital cooperation internship。
- 如果 UN Careers 页面无法直接被搜索工具索引，请返回 UN Careers 官方检索入口并在备注中写“需在 UN Careers 站内以 Internship 过滤核查”，不要写成没有机会。
- 对 UNDP、UNEP、UNESCO、UNIDO、UNCTAD、UN-Habitat 也要优先找明确的 internship 页面或岗位检索入口。
- instant 模式中，若有符合条件的国际组织 internship，至少返回 3 条 internship；weekly 模式至少返回 5 条 internship。
- 不要返回 consultant、staff position、volunteer、full-time job 或 fellowship 来冒充 internship。

NGO / Think Tank 专项检索要求：
- 扩展监测大型 NGO、foundation、policy institute、think tank 的 fellowship、internship、young professionals、research assistant、policy school、conference 和 call for applications。
- 优先保留中性、技术性、发展政策、气候治理、国际金融/债务、AI治理、全球治理、多边合作、国际组织能力建设相关机会。
- 对明显以 China threat、sanctions、decoupling、democracy promotion、authoritarian influence、Taiwan Strait security、Xinjiang / Uyghur / Tibet advocacy、人权倡议、军事安全或国防政策为核心框架的机会，必须写入“排除原因”，行动优先级设为低，默认不推荐进入主视图。
- 对 NED、Freedom House、Human Rights Watch、Amnesty、security/defense think tanks 等来源，除非机会主题明确是非敏感的全球治理、发展、气候或国际组织能力建设，否则标记为政治风险较高。
- 不要因为来源是 NGO/智库就自动收录；必须与用户的政策研究、国际组织、全球治理、发展、可持续、AI治理、气候或金融债务方向有连接。

项目规则：
{rules}

议题筛选规则：
{topic_rules}

固定监测源：
{sources}

已入库链接，尽量不要重复返回：
{existing_links}

请联网搜索并返回严格 JSON，不要返回 Markdown 代码块。格式：
{{
  "opportunities": [
    {{
      "机会名称": "名称",
      "机会类型": "国际组织年会/青年论坛/fellowship/internship/policy school/summer school/学术年会/CFP/workshop/其他",
      "机会类型分组": "会议/学术论坛/CFP/Fellowship/Internship/青年项目/Policy/Summer School/其他",
      "主办方": "主办方",
      "议题标签": "用分号分隔",
      "主题分区": "AI治理/全球治理/国际组织/可持续发展/气候/发展/不平等/国际金融/债务/国际关系/政治学/其他",
      "相关度": "高/中/低",
      "截止日期": "YYYY-MM-DD 或 待核查",
      "会议日期": "YYYY-MM-DD 或日期范围或待核查",
      "地点/线上": "地点、线上或混合",
      "原网页链接": "会议官网或信息源原始链接",
      "申请/投稿链接": "申请、报名或投稿链接；没有则待核查",
      "参加条件": "年龄、身份、学历、国籍/地区、专业背景等；没有明确写出则待核查",
      "费用": "注册费、参会费、线上/线下成本；没有明确写出则待核查",
      "是否有资助": "是/否/待核查",
      "资助说明链接": "奖学金、travel grant、fee waiver 等说明链接；没有则待核查",
      "需要准备的材料": "CV、论文摘要、statement、推荐信等；没有则待核查",
      "岗位类型": "如果是实习必须写 Internship；其他机会可留空",
      "岗位职能": "政策研究/项目支持/可持续发展/治理/发展融资/气候/AI或数字治理/传播倡导/伙伴关系/战略研究/其他/待核查",
      "排除原因": "如果 internship 是城市规划、法律、HR、IT、财务、采购、行政、医学、工程等强专业壁垒岗位，或 NGO/智库机会存在较高政治风险，写明原因；否则留空",
      "行动优先级": "高/中高/中/低",
      "状态": "新发现/待核查/值得申请/已错过/长期关注",
      "备注": "一句话说明为什么值得关注，或为什么只是低优先级"
    }}
  ]
}}

数量要求：
- instant 模式返回 8-15 条近期新机会或近期开放的周期性机会。
- weekly 模式返回 15-25 条，包括新增、即将截止、fellowship、internship 和 CFP。
- Internship 必须明确是 internship；不要返回 full-time job、consultant、volunteer 或 staff position。
- Internship 如果偏城市规划、法律、HR、IT、财务、采购、行政、医学、工程等强专业壁垒，允许返回但必须写排除原因并标为低优先级。
- NGO/智库机会如果存在明显政治风险，允许返回但必须写排除原因并标为低优先级；中性发展、气候、AI治理、国际金融和全球治理机会优先。
- 不要虚构截止日期、资助、资格或链接；不确定就写“待核查”。
- 原网页链接必须是真实可核查链接。
"""


def call_openai(prompt: str) -> str:
    from openai import OpenAI

    model = os.environ.get("OPENAI_MODEL", "gpt-5.5")
    client = OpenAI()
    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        tool_choice="auto",
        input=prompt,
    )
    return response.output_text


def parse_opportunities(raw: str, today: str) -> list[dict[str, str]]:
    try:
        data = json.loads(strip_json_fence(raw))
    except json.JSONDecodeError as exc:
        print(raw, file=sys.stderr)
        raise RuntimeError("OpenAI 返回内容不是有效 JSON。") from exc

    items = data.get("opportunities", [])
    if not isinstance(items, list):
        raise RuntimeError("JSON 中缺少 opportunities 数组。")

    rows = [normalize_row(item, today) for item in items if isinstance(item, dict)]
    valid = [row for row in rows if row.get("机会名称") and row.get("原网页链接")]
    if not valid:
        raise RuntimeError("没有得到带原网页链接的有效机会。")
    return valid


def row_badge(row: dict[str, str]) -> str:
    related = row.get("相关度", "")
    if related == "高":
        return "高相关"
    if "fellow" in row.get("机会类型", "").lower() or "fellowship" in row.get("机会名称", "").lower():
        return "Fellowship"
    return row.get("机会类型", "机会")


def card_tone(row: dict[str, str]) -> tuple[str, str, str]:
    related = row.get("相关度", "")
    if related == "高":
        return "#2f6f73", "#edf7f6", "#d6e9e7"
    if related == "中":
        return "#7a5c2e", "#faf5ec", "#eadcc8"
    return "#6b7280", "#f3f4f6", "#e5e7eb"


def detail_item(label: str, value: str) -> str:
    clean_value = html.escape(value or "待核查")
    clean_label = html.escape(label)
    return f"""
      <li style="margin:7px 0;padding-left:2px;">
        <span style="font-weight:700;color:#1f2937;">{clean_label}：</span>{clean_value}
      </li>
    """


def combined_text(row: dict[str, str]) -> str:
    return " ".join(str(value).lower() for value in row.values())


def matched_focus_areas(row: dict[str, str]) -> list[str]:
    text = combined_text(row)
    areas = []
    for area, keywords in PERSONAL_FOCUS.items():
        if any(keyword.lower() in text for keyword in keywords):
            areas.append(area)
    return areas


def has_clear_deadline(row: dict[str, str]) -> bool:
    deadline = row.get("截止日期", "").strip()
    return bool(deadline) and "待核查" not in deadline and "rolling" not in deadline.lower()


def is_fellowship(row: dict[str, str]) -> bool:
    text = (row.get("机会类型", "") + " " + row.get("机会名称", "")).lower()
    return "fellow" in text or "fellowship" in text


def is_academic_submission(row: dict[str, str]) -> bool:
    text = (row.get("机会类型", "") + " " + row.get("机会名称", "") + " " + row.get("需要准备的材料", "")).lower()
    return "cfp" in text or "call for papers" in text or "投稿" in text or "论文摘要" in text or "abstract" in text


def is_international_org(row: dict[str, str]) -> bool:
    text = combined_text(row)
    org_terms = ["world bank", "imf", "united nations", "un ", "oecd", "undp", "unctad", "unfccc", "国际组织", "联合国", "世界银行"]
    return any(term in text for term in org_terms)


def personal_fit(row: dict[str, str]) -> str:
    areas = matched_focus_areas(row)
    related = row.get("相关度", "")
    area_text = "、".join(areas[:3])

    if related == "低" and not areas:
        return "与你目前想强化的发展、全球治理、气候、AI、金融债务主线距离较远，除非后续页面显示有明确交叉，否则不建议投入太多精力。"
    if is_fellowship(row) and areas:
        return f"匹配度偏高。它同时符合你想拓展经历厚度的目标和“{area_text}”方向，fellowship 也比普通会议更容易沉淀成简历上的清晰经历。"
    if is_academic_submission(row) and areas:
        return f"匹配度中高。它适合把你的研究兴趣往“{area_text}”方向收束成摘要或短论文，但前提是你能复用已有选题，而不是临时从零开题。"
    if is_international_org(row) and areas:
        return f"匹配度高。主办方背书和你的“国际组织/全球治理”目标一致，尤其适合作为信息入口和 networking 机会。"
    if areas:
        return f"主题匹配度不错，主要落在“{area_text}”。它值得先进入观察清单，再看资格和材料是否轻量。"
    return "目前只能算弱匹配。可以保留链接，但不应该挤占 fellowship、国际组织青年项目或高相关 CFP 的准备时间。"


def investment_judgment(row: dict[str, str]) -> str:
    related = row.get("相关度", "")
    materials = row.get("需要准备的材料", "")
    requirements = row.get("参加条件", "")
    uncertain = "待核查" in (materials + requirements + row.get("申请/投稿链接", ""))

    if related == "低":
        return "低投入：收藏即可，不建议立刻准备材料。"
    if is_fellowship(row):
        if uncertain:
            return "中高投入：先用 15 分钟确认资格和周期；如果开放申请，再投入时间准备英文 CV、statement 和推荐人。"
        return "高投入：如果资格符合，值得认真准备，因为 fellowship 对经历厚度的提升通常强于普通参会。"
    if is_academic_submission(row):
        return "选择性投入：只有当你能用现有研究兴趣快速改出摘要时才值得投；如果需要重开一个陌生题目，投入产出比会下降。"
    if is_international_org(row) and has_clear_deadline(row):
        return "中高投入：建议当天打开原网页确认报名通道，国际组织机会的窗口期往往不长。"
    if is_international_org(row):
        return "中等投入：先设为长期关注，重点盯后续 registration、youth delegate 或 side event 入口。"
    if related == "高":
        return "中等投入：主题值得，但先不要写材料；先确认资格、截止时间和是否真的有可申请入口。"
    return "轻投入：保留在数据库中，等出现明确投稿、申请或青年通道后再行动。"


def render_rows(rows: list[dict[str, str]]) -> str:
    cards = []
    for index, row in enumerate(rows, start=1):
        title = html.escape(row.get("机会名称", "未命名机会"))
        original = html.escape(row.get("原网页链接", ""))
        apply_url = html.escape(row.get("申请/投稿链接", ""))
        badge = html.escape(row_badge(row))
        accent, chip_bg, chip_border = card_tone(row)
        cards.append(
            f"""
            <section style="border:1px solid #e2e8f0;border-radius:10px;margin:14px 0;background:#ffffff;">
              <div style="padding:18px 18px 16px;border-left:4px solid {accent};">
              <div style="font-size:12px;letter-spacing:0;color:#6b7280;margin-bottom:8px;">#{index:02d} · {html.escape(row.get("主办方", "待核查"))}</div>
              <div style="display:inline-block;background:{chip_bg};border:1px solid {chip_border};border-radius:999px;padding:3px 10px;font-size:12px;color:{accent};font-weight:700;">{badge}</div>
              <h2 style="font-size:19px;line-height:1.35;margin:9px 0 8px;color:#111827;">{title}</h2>
              <p style="margin:0 0 12px;color:#6b7280;font-size:14px;">{html.escape(row.get("机会类型", "待核查"))} · 相关度 {html.escape(row.get("相关度", "待核查"))}</p>
              <ul style="margin:10px 0 0;padding-left:20px;color:#4b5563;">
                {detail_item("主题", row.get("议题标签", "待核查"))}
                {detail_item("截止时间", row.get("截止日期", "待核查"))}
                {detail_item("项目/会议日期", row.get("会议日期", "待核查"))}
                {detail_item("地点/形式", row.get("地点/线上", "待核查"))}
                {detail_item("材料", row.get("需要准备的材料", "待核查"))}
                {detail_item("要求", row.get("参加条件", "待核查"))}
              </ul>
              <div style="margin-top:14px;padding:12px 13px;background:#f8fafc;border:1px solid #e5e7eb;border-radius:8px;color:#374151;font-size:14px;">
                <div style="font-weight:800;color:#111827;margin-bottom:4px;">个人匹配度</div>
                <div>{html.escape(personal_fit(row))}</div>
                <div style="font-weight:800;color:#111827;margin:10px 0 4px;">投入判断</div>
                <div>{html.escape(investment_judgment(row))}</div>
              </div>
              <p style="margin:10px 0 0;color:#6b7280;font-size:13px;">{html.escape(row.get("备注", ""))}</p>
              <p style="margin:12px 0 0;">
                <a href="{original}" style="color:#0b5cad;font-weight:700;">原网页链接</a>
                {f' ｜ <a href="{apply_url}" style="color:#0b5cad;font-weight:700;">申请/投稿链接</a>' if apply_url and apply_url != "待核查" else ""}
              </p>
              </div>
            </section>
            """
        )
    return "\n".join(cards)


def build_overall_advice(rows: list[dict[str, str]]) -> str:
    high_count = sum(1 for row in rows if row.get("相关度") == "高")
    fellowship_count = sum(
        1 for row in rows
        if "fellow" in (row.get("机会类型", "") + " " + row.get("机会名称", "")).lower()
    )
    cfp_count = sum(1 for row in rows if "cfp" in row.get("机会类型", "").lower() or "投稿" in row.get("机会类型", ""))
    parts = [
        f"本次共有 {len(rows)} 条机会，其中 {high_count} 条高相关。",
        "你的主要短板不是判断力，而是入口分散和开放时间不透明，所以第一轮建议先广收、快看、轻筛。",
    ]
    if fellowship_count:
        parts.append(f"其中 {fellowship_count} 条带有 fellowship 属性，建议提前维护一版英文 CV、个人陈述和推荐人名单。")
    if cfp_count:
        parts.append(f"其中 {cfp_count} 条偏学术投稿，适合和已有研究兴趣合并成 1-2 个可反复改写的摘要。")
    parts.append("真正值得马上行动的机会，是主题贴合、截止时间明确、材料要求不复杂的交集。")
    return " ".join(parts)


def build_email(rows: list[dict[str, str]], mode: str, today: str) -> str:
    title = "国际机会雷达已更新"
    dashboard_url = os.environ.get("DASHBOARD_URL", "").strip()
    top_rows = rows[:3]
    top_items = "".join(
        f"<li>{html.escape(row.get('机会名称', '未命名机会'))} · {html.escape(row.get('行动优先级', ''))}</li>"
        for row in top_rows
    )
    dashboard_link = (
        f'<p style="margin:16px 0 0;"><a href="{html.escape(dashboard_url)}" style="color:#0b5cad;font-weight:700;">打开网页仪表盘</a></p>'
        if dashboard_url
        else '<p style="margin:16px 0 0;color:#6b7280;">仪表盘已生成到 docs/index.html，可在 GitHub Pages 打开。</p>'
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
</head>
<body style="margin:0;background:#f4f6f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC',sans-serif;line-height:1.65;color:#1f2937;">
  <main style="max-width:760px;margin:0 auto;padding:28px 18px;">
    <header style="background:#ffffff;border:1px solid #e2e8f0;border-radius:12px;padding:22px 22px 20px;margin-bottom:18px;">
      <div style="font-size:13px;color:#6b7280;margin-bottom:4px;">{today}</div>
      <h1 style="font-size:27px;line-height:1.25;margin:0;color:#111827;">{html.escape(title)}</h1>
      <p style="margin:10px 0 0;color:#4b5563;">今天新增或更新 {len(rows)} 条机会。邮件不再展开长列表，请到网页仪表盘按类型、主题和截止时间筛选。</p>
      <ul style="margin:14px 0 0;padding-left:20px;color:#4b5563;">{top_items}</ul>
      {dashboard_link}
    </header>
  </main>
</body>
</html>
"""


def safe_filename(value: str) -> str:
    value = re.sub(r"[\\/:*?\"<>|]+", "-", value)
    value = re.sub(r"\s+", "-", value).strip("-")
    return value[:80] or "opportunity-radar"


def write_email(rows: list[dict[str, str]], mode: str, today: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    suffix = "机会提醒" if mode == "instant" else "每周汇总"
    path = OUTPUT_DIR / f"{today}-{safe_filename(suffix)}.html"
    path.write_text(build_email(rows, mode, today), encoding="utf-8")
    return path


def set_github_output(**values: str) -> None:
    output = os.environ.get("GITHUB_OUTPUT")
    if not output:
        return
    with open(output, "a", encoding="utf-8") as file:
        for key, value in values.items():
            file.write(f"{key}={value}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["instant", "weekly"], default="instant")
    args = parser.parse_args()

    load_env(API_ENV_PATH)
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    existing = load_csv(DB_PATH, FIELDS)
    prompt = build_prompt(today, args.mode, existing)
    incoming = parse_opportunities(call_openai(prompt), today)
    merged, new_rows = merge_rows(existing, incoming)
    write_csv(DB_PATH, FIELDS, merged)

    notified = load_notified_fingerprints()
    if args.mode == "instant":
        alert_rows = [row for row in new_rows if row.get("链接指纹") not in notified]
    else:
        alert_rows = incoming or merged[:25]

    if not alert_rows:
        print("No new opportunities to alert.")
        set_github_output(has_updates="false", new_count="0", dashboard_path="docs/index.html")
        return 0

    html_path = write_email(alert_rows, args.mode, today)
    append_notified(alert_rows, args.mode, today)
    subject = "【国际机会雷达】仪表盘已更新"
    set_github_output(
        has_updates="true",
        new_count=str(len(alert_rows)),
        dashboard_path="docs/index.html",
        html_path=str(html_path.relative_to(PROJECT_DIR)),
        email_subject=subject,
    )
    print(f"Updated database: {DB_PATH.relative_to(PROJECT_DIR)}")
    print(f"Wrote email: {html_path.relative_to(PROJECT_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
