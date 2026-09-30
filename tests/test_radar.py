import argparse
import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00-自动化"))
import collect_opportunities as radar
import collection_pipeline as pipeline
import eligibility
import generate_dashboard as dashboard

URL = "https://example.org/jobs/policy-analyst"
TEXT = "Policy Analyst. Coordinate international climate policy research. No work experience is required. Recent graduates may apply. Applicants must have authorization to work in the US. We do not provide visa sponsorship. OPT candidates are welcome."


def page(text=TEXT):
    return {"url": URL, "text": text, "links": [], "hash": "hash-one", "source_id": "example"}


def opportunity():
    return {"title": "Graduate Policy Analyst", "host": "Example Institute", "group": "Early-career Jobs", "topic": "可持续发展/气候", "tags": "climate policy", "deadline": "", "dates": "", "location": "US", "source_url": URL, "apply_url": URL, "batch": "", "materials": ["CV", "Cover letter"], "function": "International climate policy coordination", "judgment": "Policy-focused role open to graduates.", "relevant_duties": True, "specialized_duties": False, "senior_role": False, "scope_quote": "Coordinate international climate policy research.", "risk_note": "", "risk_quote": "", "eligibility": [{"category": "experience", "status": "Required", "summary": "No work experience required", "quote": "No work experience is required.", "url": URL, "min_years": None}]}


def payload(item=None):
    return {"pages": [{"url": URL, "reason": "Current graduate vacancy", "opportunities": [item or opportunity()]}]}


class EligibilityTests(unittest.TestCase):
    def test_missing_page_preserves_other_page_results(self):
        missing = {**page(), "url": "https://example.org/missing"}
        rows, rejected = pipeline.validate_batch(payload(), [page(), missing], "2026-09-30")
        self.assertEqual(len(rows), 1)
        self.assertIn(missing["url"], rejected)
        self.assertNotIn(URL, rejected)

    def test_duplicate_decision_is_not_cached_as_valid(self):
        data = payload()
        data["pages"].append(copy.deepcopy(data["pages"][0]))
        rows, rejected = pipeline.validate_batch(data, [page()], "2026-09-30")
        self.assertEqual(rows, [])
        self.assertIn(URL, rejected)

    def test_schema_requires_all_supplied_pages(self):
        schema = pipeline.extraction_schema([URL, "https://example.org/second"])
        self.assertEqual(schema["properties"]["pages"]["minItems"], 2)
        self.assertEqual(schema["properties"]["pages"]["maxItems"], 2)

    def test_policy_intern_ranks_above_senior_links(self):
        links = [{"title": "Senior Climate Policy Lead", "url": "https://example.org/senior"},
                 {"title": "Careers", "url": "https://example.org/careers"},
                 {"title": "Restoration Finance & Policy Intern", "url": "https://example.org/intern"}]
        self.assertEqual(pipeline.ranked_links(links, "jobs", {}, "2026-09-30")[0]["url"], links[2]["url"])

    def test_publications_and_archives_do_not_fill_event_queue(self):
        listing = {"url": URL, "links": [{"title": "Governance Conference", "url": "https://example.org/publication/governance"}, {"title": "Conference Archive", "url": "https://example.org/archive"}, {"title": "Call for Papers", "url": "https://example.org/cfp"}]}
        self.assertEqual(len(pipeline.candidate_links(listing, "academic")), 1)
    def test_english_politics_and_governance_relevance(self):
        row = radar.normalize_row({"机会名称": "Political Science and International Relations Congress", "原网页链接": URL}, "2026-09-30")
        self.assertEqual(row["相关度"], "高")

    def test_conference_submission_calls_use_academic_category(self):
        row = radar.normalize_row({"机会名称": "DSA2027 Call for Panels", "机会类型分组": "会议", "原网页链接": URL}, "2026-09-30")
        self.assertEqual(row["机会类型分组"], "学术论坛/CFP")

    def test_deadline_recovery_uses_source_order_not_model_paraphrase(self):
        source = "9 November 2026 Call for S ection Proposals D eadline 9 December 2026 Abstract Submission Opens 16 February 2027 Abstract Submission Deadline"
        evidence = pipeline.deadline_evidence("2026-11-09", "Call for Section Proposals Deadline: 9 November 2026", source)
        self.assertIn(evidence, source)
        with self.assertRaises(ValueError):
            pipeline.deadline_evidence("2026-12-09", "Submission deadline 9 December 2026", source)

    def test_expired_record_is_skipped_before_other_validation(self):
        item = opportunity()
        item["deadline"] = "2026-06-14"
        item["scope_quote"] = "invalid"
        self.assertEqual(pipeline.validate_extraction(payload(item), [page()], "2026-09-30"), [])

    def test_bad_record_does_not_discard_valid_batch_records(self):
        good, bad = opportunity(), opportunity()
        bad["scope_quote"] = "invented evidence"
        data = payload(good)
        data["pages"][0]["opportunities"].append(bad)
        rows, rejected = pipeline.validate_batch(data, [page()], "2026-09-30")
        self.assertEqual(len(rows), 1)
        self.assertIn(URL, rejected)

    def test_deadline_must_match_verbatim_phase_evidence(self):
        item = opportunity()
        item["deadline"] = "2026-11-09"
        item["deadline_quote"] = "9 November 2026 Section proposals deadline"
        self.assertEqual(len(pipeline.validate_extraction(payload(item), [page(TEXT + item["deadline_quote"])], "2026-09-30")), 1)
        item["deadline"] = "2027-02-16"
        with self.assertRaises(ValueError):
            pipeline.validate_extraction(payload(item), [page(TEXT + item["deadline_quote"])], "2026-09-30")

    def test_budget_balances_opportunity_categories(self):
        candidates = [{"url": str(i), "source": {"id": source, "kind": kind}}
                      for i, (source, kind) in enumerate([("jobs-a", "jobs"), ("jobs-a", "jobs"), ("jobs-b", "jobs"), ("ecpr", "academic"), ("school", "schools")])]
        ordered = pipeline.balanced_candidates(candidates)
        self.assertEqual({c["source"]["kind"] for c in ordered[:3]}, {"jobs", "academic", "schools"})
        self.assertEqual(len(ordered), len(candidates))

    def test_all_seven_opportunity_categories_get_a_turn(self):
        kinds = ["jobs", "academic", "youth", "events", "fellowship", "scholarships", "schools"]
        candidates = [{"url": f"{kind}/{i}", "source": {"id": kind, "kind": kind}}
                      for kind in kinds for i in range(5)]
        ordered = pipeline.balanced_candidates(candidates)
        self.assertEqual([c["source"]["kind"] for c in ordered[:7]], kinds)

    def test_scholarship_category_does_not_use_job_experience_exclusion(self):
        item = opportunity()
        item["group"] = "Scholarships"
        quote = "Two years of professional experience required."
        item["eligibility"] = [{"category": "experience", "status": "Required", "summary": "Two years required", "quote": quote, "url": URL, "min_years": 2}]
        row = pipeline.validate_extraction(payload(item), [page(TEXT + quote)], "2026-09-30")[0]
        self.assertEqual(row["机会类型分组"], "Scholarships")
        self.assertFalse(row["排除原因"])
        self.assertIn('data-filter-type="Scholarships"', dashboard.render_dashboard([row]))

    def test_forums_and_youth_calls_are_discoverable(self):
        listing = {"url": URL, "links": [
            {"title": "Youth Forum Registration", "url": "https://example.org/forum"},
            {"title": "Call for Panels 2027", "url": "https://example.org/panels"},
            {"title": "Publications", "url": "https://example.org/publications"}]}
        links = pipeline.candidate_links(listing, "youth")
        self.assertEqual(len(links), 2)
        self.assertEqual(pipeline.ranked_links(links, "youth", {}, "2026-09-30")[0]["url"], "https://example.org/forum")

    def test_search_covers_more_than_recruitment(self):
        prompt = pipeline.discovery_prompt([{"name": "IPPA", "kind": "academic"}, {"name": "UN Youth Office", "kind": "youth"}], "2026-09-30")
        for text in ["CFPs", "youth participation", "fellowships", "schools", "IPPA", "UN Youth Office"]:
            self.assertIn(text, prompt)

    def test_zero_experience_role_is_retained(self):
        row = pipeline.validate_extraction(payload(), [page()], "2026-09-30")[0]
        self.assertEqual(row["排除原因"], "")
        self.assertEqual(row["最近核查日期"], "2026-09-30")

    def test_explicit_no_experience_is_valid_zero_without_year_word(self):
        item = opportunity()
        item["eligibility"][0]["min_years"] = 0
        row = pipeline.validate_extraction(payload(item), [page()], "2026-09-30")[0]
        self.assertEqual(row["排除原因"], "")

    def test_required_year_excluded_but_preferred_retained(self):
        for status, excluded in [("Required", True), ("Preferred", False)]:
            item = opportunity()
            quote = "One year of professional experience is " + status.lower() + "."
            item["eligibility"] = [{"category": "experience", "status": status, "summary": quote, "quote": quote, "url": URL, "min_years": 1}]
            row = pipeline.validate_extraction(payload(item), [page(TEXT + quote)], "2026-09-30")[0]
            self.assertEqual(bool(row["排除原因"]), excluded)

    def test_zero_to_two_years_not_excluded(self):
        item = opportunity()
        quote = "0-2 years of professional experience required."
        item["eligibility"] = [{"category": "experience", "status": "Required", "summary": "0-2 years", "quote": quote, "url": URL, "min_years": 0}]
        row = pipeline.validate_extraction(payload(item), [page(TEXT + quote)], "2026-09-30")[0]
        self.assertFalse(row["排除原因"])

    def test_unknown_experience_is_not_filtered(self):
        item = opportunity()
        item["eligibility"] = []
        row = pipeline.validate_extraction(payload(item), [page()], "2026-09-30")[0]
        self.assertFalse(row["排除原因"])
        self.assertEqual(row["经验门槛"], "Not stated")

    def test_citizenship_not_inferred_from_us_or_no_sponsorship(self):
        facts = eligibility.validate_facts([
            {"category": "visa_sponsorship", "status": "Required", "summary": "No sponsorship provided", "quote": "We do not provide visa sponsorship.", "url": URL, "min_years": None},
            {"category": "opt_cpt", "status": "Required", "summary": "OPT accepted", "quote": "OPT candidates are welcome.", "url": URL, "min_years": None},
        ], {URL: TEXT})
        self.assertEqual(next(f for f in facts if f["category"] == "citizenship")["status"], "Not stated")
        self.assertEqual(next(f for f in facts if f["category"] == "opt_cpt")["summary"], "OPT accepted")

    def test_china_requirements_evidence_and_status(self):
        source = "中共党员优先。仅限985/211高校应届毕业生。"
        facts = eligibility.validate_facts([
            {"category": "party_membership", "status": "Preferred", "summary": "CCP membership preferred", "quote": "中共党员优先", "url": URL, "min_years": None},
            {"category": "school_restrictions", "status": "Required", "summary": "985/211 graduates only", "quote": "仅限985/211高校应届毕业生", "url": URL, "min_years": None},
        ], {URL: source})
        self.assertEqual(next(f for f in facts if f["category"] == "party_membership")["status"], "Preferred")

    def test_fabricated_condition_or_link_rejected(self):
        item = opportunity()
        item["eligibility"][0]["quote"] = "US citizens only"
        with self.assertRaises(ValueError):
            pipeline.validate_extraction(payload(item), [page()], "2026-09-30")
        item = opportunity()
        item["apply_url"] = "https://invented.invalid/job"
        with self.assertRaises(ValueError):
            pipeline.validate_extraction(payload(item), [page()], "2026-09-30")

    def test_generic_admin_coordination_hidden(self):
        item = opportunity()
        item["relevant_duties"] = False
        row = pipeline.validate_extraction(payload(item), [page()], "2026-09-30")[0]
        self.assertTrue(row["排除原因"])

    def test_no_internship_marker_rejected(self):
        item = opportunity()
        item["group"] = "Internship"
        with self.assertRaises(ValueError):
            pipeline.validate_extraction(payload(item), [page()], "2026-09-30")


class CollectionTests(unittest.TestCase):
    def test_empty_invalid_and_incomplete_response_fail(self):
        with tempfile.TemporaryDirectory() as folder:
            for status, text in [("completed", ""), ("completed", "not json"), ("incomplete", '{"pages":[]}'), ("completed", '{"pages":[]}')]:
                with self.assertRaises(ValueError):
                    pipeline.response_json(SimpleNamespace(status=status, output_text=text), Path(folder) / "error.json")

    def test_health_partial_failed_and_verified_zero(self):
        self.assertEqual(pipeline.health_outcome({"a": {"status": "checked"}}, 0, []), "success")
        self.assertEqual(pipeline.health_outcome({"a": {"status": "checked"}, "b": {"status": "failed"}}, 0, []), "partial")
        self.assertEqual(pipeline.health_outcome({"a": {"status": "failed"}}, 0, []), "failed")
        self.assertEqual(pipeline.health_outcome({"a": {"status": "partial", "validated_pages": 1}}, 1, []), "partial")

    def test_normalization_never_fake_verifies_old_rows(self):
        row = radar.normalize_row({"机会名称": "Old", "原网页链接": URL, "最近核查日期": "2026-07-10"}, "2026-09-30")
        self.assertEqual(row["最近核查日期"], "2026-07-10")

    def test_cross_source_dedup_and_archive_id_preserved(self):
        old = {"机会名称": "Policy Analyst", "原网页链接": URL, "申请/投稿链接": URL, "链接指纹": "legacy-archive-id", "发现日期": "2026-07-10", "状态": "长期关注"}
        new = {**old, "原网页链接": "https://example.org/news/new-role", "链接指纹": "new-id", "发现日期": "2026-09-30", "参加条件": "Graduate"}
        rows, added = pipeline.merge_verified([old], [new])
        self.assertEqual(len(rows), 1)
        self.assertEqual(added, [])
        self.assertEqual(rows[0]["链接指纹"], "legacy-archive-id")
        self.assertEqual(rows[0]["发现日期"], "2026-07-10")

    def test_same_url_new_cohort_is_new_opportunity(self):
        old = {"机会名称": "2026 Fellowship", "原网页链接": URL, "发布批次": "2026"}
        new = {"机会名称": "2027 Fellowship", "原网页链接": URL, "发布批次": "2027"}
        rows, added = pipeline.merge_verified([old], [new])
        self.assertEqual(len(rows), 2)
        self.assertEqual(len(added), 1)

    def test_failed_run_keeps_database_and_success_date(self):
        self.run_fixture(failure=True)

    def test_actual_new_record_written_by_pipeline(self):
        self.run_fixture(failure=False)

    def test_unexpected_error_updates_failure_status(self):
        with tempfile.TemporaryDirectory() as folder:
            status = Path(folder) / "status.json"
            pipeline.atomic_json(status, {"status": "partial", "last_successful_collection": "previous-success"})
            with patch.object(pipeline, "STATUS_PATH", status), patch.object(pipeline, "run", side_effect=TypeError("unexpected")), patch.object(sys, "argv", ["radar"]):
                self.assertEqual(pipeline.main(), 1)
            report = json.loads(status.read_text())
            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["last_successful_collection"], "previous-success")
            self.assertIn("TypeError", report["errors"][0])

    def test_discovery_then_extraction_executes_without_real_model_calls(self):
        self.run_fixture(failure=False, discovery=True)

    def run_fixture(self, failure, discovery=False):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            db = root / "db.csv"
            radar.write_csv(db, radar.FIELDS, [{"机会名称": "Old", "原网页链接": "https://example.org/old", "发现日期": "2026-07-10", "最近核查日期": "2026-07-10"}])
            original = db.read_bytes()
            status = root / "status.json"
            pipeline.atomic_json(status, {"last_successful_collection": "previous-success", "sources": {"example": {"last_success": None}, "example2": {"last_success": None}}})
            sources = root / "sources.json"
            pipeline.atomic_json(sources, [{"id": source_id, "name": "Example", "url": URL, "domains": ["example.org"], "kind": "jobs"} for source_id in ["example", "example2"]])
            fetched = page()
            fetched["links"] = [{"url": URL, "title": "Policy Analyst"}]
            fetcher = SimpleNamespace(fetch=lambda *args: copy.deepcopy(fetched))
            args = argparse.Namespace(probe=False, limit_sources=0, no_discovery=not discovery, mode="weekly")
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": "", "GITHUB_OUTPUT": ""}), patch.object(radar, "DB_PATH", db), patch.object(radar, "PROJECT_DIR", root), patch.object(radar, "OUTPUT_DIR", root / "emails"), patch.object(pipeline, "STATUS_PATH", status), patch.object(pipeline, "CACHE_PATH", root / "cache.json"), patch.object(pipeline, "SOURCES_PATH", sources), patch.object(pipeline, "indexed_discovery", return_value=([], {"status": "checked"})), patch.object(pipeline, "extract_pages", side_effect=ValueError("bad JSON") if failure else None, return_value=payload()):
                code = pipeline.run(args, client=object(), fetcher=fetcher)
            report = json.loads(status.read_text())
            self.assertIn("last_attempt", json.loads((root / "cache.json").read_text())["pages"][URL])
            if failure:
                self.assertEqual(code, 1)
                self.assertEqual(db.read_bytes(), original)
                self.assertEqual(report["last_successful_collection"], "previous-success")
            else:
                self.assertEqual(code, 0)
                self.assertEqual(report["new_count"], 1)
                self.assertEqual(len(radar.load_csv(db, radar.FIELDS)), 2)

    def test_direct_linkedin_and_private_urls_disallowed(self):
        self.assertFalse(pipeline.is_allowed("https://linkedin.com/jobs/view/123", ["example.org"]))
        self.assertFalse(pipeline.is_allowed("http://example.org", ["example.org"]))
        self.assertFalse(pipeline.is_allowed("https://example.org.evil.com", ["example.org"]))

    def test_dashboard_dynamic_dates_and_safe_embedding(self):
        result = dashboard.render_dashboard([{ "机会名称": "</script><script>alert(1)</script>", "原网页链接": URL}])
        self.assertIn("Early-career Jobs", result)
        self.assertIn("relativeKey(-29)", result)
        self.assertNotIn('const todayKey = "', result)
        self.assertNotIn("</script><script>alert(1)</script>", result)
        self.assertIn("opportunityRadarArchived", result)
        self.assertNotIn('<details class="collection-health">', result)
        self.assertNotIn("HTTPError:", result)


if __name__ == "__main__":
    unittest.main()
