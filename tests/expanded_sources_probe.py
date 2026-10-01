"""Read the newly configured publisher entries without making model calls."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "00-自动化"))
import collection_pipeline as pipeline

IDS = {"bisa", "apsa", "ipsa-congress", "acuns", "ssrc", "iias", "unfccc-fellowships", "worldbank-youth"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=sorted(IDS))
    args = parser.parse_args()
    sources = pipeline.read_json(pipeline.SOURCES_PATH, [])
    fetcher = pipeline.Fetcher()
    results = []
    for source in sources:
        if source["id"] not in IDS:
            continue
        if args.source and source["id"] != args.source:
            continue
        for url in dict.fromkeys([source["url"]] + source.get("entry_urls", [])):
            item = {"source_id": source["id"], "url": url}
            try:
                page = fetcher.fetch(url, source["domains"])
                candidates = pipeline.candidate_links(page, source["kind"])
                item.update(status="readable", final_url=page["url"], characters=len(page["text"]), candidate_count=len(candidates), examples=candidates[:5])
            except Exception as exc:
                item.update(status="failed", error=f"{type(exc).__name__}: {exc}")
            results.append(item)
            print(json.dumps(item, ensure_ascii=False), flush=True)
    path = pipeline.radar.PROJECT_DIR / "05-历史记录/expanded_sources_probe.json"
    if args.source:
        previous = pipeline.read_json(path, {}).get("results", [])
        results = [item for item in previous if item["source_id"] != args.source] + results
    pipeline.atomic_json(path, {"checked_at": datetime.now(timezone.utc).isoformat(), "model_calls": 0, "results": results})
    return 0 if any(item["status"] == "readable" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
