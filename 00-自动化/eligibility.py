"""Validate eligibility facts against the fetched source, never against a user profile."""

from __future__ import annotations

import json
import re

CATEGORIES = {
    "citizenship": "Citizenship",
    "residency": "Residency",
    "work_authorization": "Work authorization",
    "visa_sponsorship": "Visa sponsorship",
    "opt_cpt": "OPT / CPT",
    "student_graduation": "Student / graduation status",
    "education": "Education / discipline",
    "experience": "Work experience",
    "language": "Languages",
    "institution_membership": "Institution / academic association membership",
    "party_membership": "Political party membership",
    "school_restrictions": "School restrictions (985 / 211 / Double First-Class)",
}


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def validate_facts(facts: list[dict], documents: dict[str, str]) -> list[dict]:
    validated = []
    for category in CATEGORIES:
        fact = next((item for item in facts if item.get("category") == category), None)
        if not fact or fact.get("status") == "Not stated":
            validated.append({"category": category, "status": "Not stated", "summary": "", "quote": "", "url": "", "min_years": None})
            continue
        if fact.get("status") not in {"Required", "Preferred"}:
            raise ValueError("Invalid eligibility status")
        url, quote = fact.get("url", ""), fact.get("quote", "")
        if url not in documents or not compact(quote) or compact(quote) not in compact(documents[url]):
            raise ValueError(f"Unsupported eligibility evidence: {category}")
        if not fact.get("summary"):
            raise ValueError("An eligibility fact needs an English summary")
        if category == "party_membership" and not re.search(r"共产党|党员|\bCCP\b|\bCPC\b|communist party|political party", quote, re.I):
            raise ValueError("Academic association membership is not political party membership")
        years = fact.get("min_years") if category == "experience" else None
        if years is not None:
            explicit_zero = years == 0 and bool(re.search(r"no (?:prior |previous |professional |work )?experience.*required|experience (?:is )?not required|无需.*经验|经验不限", quote, re.I))
            if explicit_zero:
                validated.append({**fact, "min_years": 0})
                continue
            if category != "experience" or years < 0 or not re.search(r"\byears?\b|年", quote, re.I):
                raise ValueError("Unsupported minimum experience")
            words = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
            chinese = {0: "零", 1: "一", 2: "二", 3: "三", 4: "四", 5: "五"}
            if not re.search(rf"\b{years:g}\b|\b{words.get(years, 'not-a-number')}\b|{chinese.get(years, 'not-a-number')}年", quote, re.I):
                raise ValueError("Minimum experience does not occur in the evidence")
        validated.append({**fact, "min_years": years})
    return validated


def membership_exclusion(facts: list[dict]) -> str:
    """Apply the requested mandatory CCP membership exclusion, not a political inference."""
    fact = next((item for item in facts if item.get("category") == "party_membership"), {})
    quote = fact.get("quote", "")
    if fact.get("status") != "Required" or not quote or not fact.get("url"):
        return ""
    if not re.search(r"中共|中国共产党|党员|\bCCP\b|\bCPC\b|(?:Chinese Communist|Communist Party of China)", quote, re.I):
        return ""
    if re.search(r"优先|不限|无需|不要求|非党员.{0,12}(?:可|欢迎)|preferred|desirable|not required|not necessary|regardless of", quote, re.I):
        return ""
    # An unspecified political party or another country's communist party is not CCP evidence.
    if re.search(r"communist party", quote, re.I) and not re.search(r"China|Chinese|\bCCP\b|\bCPC\b|中共|中国共产党|党员", quote, re.I):
        return ""
    return "Requires Communist Party of China membership"


def apply_membership_filter(row: dict) -> dict:
    try:
        facts = json.loads(row.get("资格条件JSON") or "[]")
    except (ValueError, TypeError):
        return dict(row)
    if not isinstance(facts, list) or not all(isinstance(item, dict) for item in facts):
        return dict(row)
    reason = membership_exclusion(facts)
    updated = dict(row)
    if reason and reason not in updated.get("排除原因", ""):
        updated["排除原因"] = "; ".join(filter(None, [updated.get("排除原因", ""), reason]))
    return updated


def screen_role(row: dict, facts: list[dict], senior: bool, relevant: bool, specialized: bool) -> str:
    if reason := membership_exclusion(facts):
        return reason
    if row.get("机会类型分组") not in {"Internship", "Early-career Jobs"}:
        return ""
    if senior:
        return "Senior or management position; outside the graduate / zero-experience scope"
    if specialized:
        return "Core duties require a specialized technical, legal, HR, accounting or administrative background"
    if not relevant:
        return "Core duties are not connected to policy, research, international cooperation, governance or climate"
    experience = next(item for item in facts if item["category"] == "experience")
    if experience["status"] == "Required" and (experience.get("min_years") or 0) > 0:
        return f"Prior work experience required: {experience['min_years']:g} year(s)"
    if experience["status"] == "Required" and experience.get("min_years") is None and re.search(r"prior|previous|professional|相关工作|工作经验", experience.get("quote", ""), re.I):
        if not re.search(r"no (?:prior |previous |professional |work )?experience.*required|not required|无需|不限", experience["quote"], re.I):
            return "Prior work experience is explicitly required"
    return ""


def facts_json(facts: list[dict]) -> str:
    return json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
