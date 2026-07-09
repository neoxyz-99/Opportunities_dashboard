#!/usr/bin/env python3
"""Generate the static opportunity radar dashboard."""

from __future__ import annotations

import argparse
import html
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import collect_opportunities as radar


PROJECT_DIR = Path(__file__).resolve().parents[1]
CN_TZ = timezone(timedelta(hours=8))


def normalize_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    normalized = [radar.normalize_row(row, today) for row in rows]
    normalized.sort(key=lambda row: (deadline_sort_key(row), priority_sort_key(row), row.get("机会名称", "")))
    return normalized


def deadline_sort_key(row: dict[str, str]) -> str:
    deadline = row.get("截止日期", "").strip()
    if not deadline or "待核查" in deadline:
        return "9999-99-99"
    return deadline[:10]


def priority_sort_key(row: dict[str, str]) -> int:
    order = {"高": 0, "中高": 1, "中": 2, "低": 3}
    return order.get(row.get("行动优先级", ""), 4)


def visible_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if not row.get("排除原因")]


def stats(rows: list[dict[str, str]]) -> dict[str, int]:
    today = datetime.now(CN_TZ).strftime("%Y-%m-%d")
    main_rows = visible_rows(rows)
    soon = [
        row for row in main_rows
        if row.get("截止日期") and "待核查" not in row.get("截止日期", "") and row.get("截止日期", "")[:10] <= "9999-99-99"
    ]
    return {
        "total": len(main_rows),
        "today": sum(1 for row in main_rows if row.get("发现日期") == today),
        "soon": min(len(soon), len(main_rows)),
        "recommended": sum(1 for row in main_rows if row.get("行动优先级") in {"高", "中高"}),
        "needs_check": sum(1 for row in main_rows if "待核查" in " ".join(row.values())),
        "excluded": len(rows) - len(main_rows),
    }


def render_dashboard(rows: list[dict[str, str]]) -> str:
    generated_at = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M")
    data_json = json.dumps(rows, ensure_ascii=False)
    stat_json = json.dumps(stats(rows), ensure_ascii=False)
    type_buttons = "".join(
        f'<button class="filter-button" data-filter-type="{html.escape(group)}">{html.escape(group)}</button>'
        for group in ["全部"] + radar.OPPORTUNITY_GROUPS
    )
    topic_buttons = "".join(
        f'<button class="filter-button" data-filter-topic="{html.escape(topic)}">{html.escape(topic)}</button>'
        for topic in ["全部"] + radar.TOPIC_SECTIONS
    )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>国际机会雷达</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ed;
      --wash-1: rgba(214, 205, 194, .44);
      --wash-2: rgba(170, 185, 176, .32);
      --wash-3: rgba(199, 183, 170, .28);
      --panel: rgba(255, 254, 251, .82);
      --panel-solid: #fffdfa;
      --text: #2d302d;
      --muted: #72756f;
      --line: rgba(92, 100, 88, .14);
      --ink: #53645c;
      --ink-2: #6f766b;
      --soft: #ece8e0;
      --soft-2: #e2e7df;
      --accent: #7d8f84;
      --shadow: 0 18px 48px rgba(73, 69, 61, .10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 12% 10%, var(--wash-2), transparent 30%),
        radial-gradient(circle at 86% 18%, var(--wash-1), transparent 32%),
        radial-gradient(circle at 45% 92%, var(--wash-3), transparent 36%),
        var(--bg);
      color: var(--text);
      font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
      line-height: 1.58;
    }}
    .shell {{ max-width: 1200px; margin: 0 auto; padding: 34px 22px 48px; }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 24px;
      align-items: center;
      margin-bottom: 18px;
    }}
    h1 {{ margin: 0; font-size: clamp(34px, 5vw, 58px); letter-spacing: 0; line-height: .98; font-weight: 780; }}
    .meta {{ color: var(--muted); font-size: 13px; text-align: right; }}
    .stats {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 20px 0 14px; }}
    .stat {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 15px 16px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }}
    .stat strong {{ display: block; font-size: 26px; line-height: 1; font-weight: 760; }}
    .stat span {{ display: block; margin-top: 7px; color: var(--muted); font-size: 12px; }}
    .toolbar {{
      background: rgba(255, 254, 251, .78);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 16px;
      position: sticky;
      top: 12px;
      z-index: 5;
      box-shadow: var(--shadow);
      backdrop-filter: blur(18px);
    }}
    .search-row {{ display: grid; grid-template-columns: 1fr auto auto auto; gap: 10px; }}
    input, select {{
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 13px;
      background: rgba(255,255,255,.82);
      color: var(--text);
      padding: 0 12px;
      font-size: 14px;
    }}
    .filter-section {{ margin-top: 12px; }}
    .filter-label {{ color: var(--muted); font-size: 12px; margin-bottom: 8px; }}
    .filters {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    .filter-button {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,.74);
      border-radius: 999px;
      padding: 8px 13px;
      color: #4d564f;
      cursor: pointer;
      font-size: 13px;
    }}
    .filter-button.active {{ background: #5d6b62; color: #fff; border-color: #5d6b62; }}
    .content {{ margin-top: 18px; }}
    .list {{ display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 14px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      box-shadow: var(--shadow);
      overflow: hidden;
      backdrop-filter: blur(18px);
      grid-column: span 6;
      position: relative;
    }}
    .card::before {{ content: ""; position: absolute; inset: 0; pointer-events: none; background: linear-gradient(135deg, rgba(255,255,255,.38), transparent 45%); }}
    .card.excluded {{ opacity: .62; }}
    .card summary {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      padding: 18px 18px 16px;
      cursor: pointer;
      list-style: none;
      position: relative;
    }}
    .card summary::-webkit-details-marker {{ display: none; }}
    .title {{ font-size: 17px; font-weight: 760; margin: 0 0 10px; line-height: 1.34; }}
    .chips {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .chip {{ border-radius: 999px; padding: 4px 10px; font-size: 12px; background: var(--soft); color: var(--ink); }}
    .chip.topic {{ background: var(--soft-2); color: var(--ink); }}
    .chip.priority {{ background: #eee4d7; color: #725f4e; }}
    .deadline {{ min-width: 110px; text-align: right; color: var(--muted); font-size: 13px; }}
    .deadline strong {{ display: block; color: var(--text); font-size: 15px; }}
    .details {{ border-top: 1px solid var(--line); padding: 16px 18px 18px; position: relative; }}
    .detail-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    .field {{ background: rgba(248, 247, 242, .76); border: 1px solid var(--line); border-radius: 14px; padding: 11px 12px; }}
    .field b {{ display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; }}
    .field span {{ font-size: 14px; }}
    .judgment {{ margin-top: 12px; padding: 13px; border: 1px solid var(--line); background: rgba(246, 244, 238, .70); border-radius: 16px; }}
    .links {{ margin-top: 13px; display: flex; flex-wrap: wrap; gap: 10px; }}
    .links a {{ color: #53645c; font-weight: 750; text-decoration: none; border-bottom: 1px solid rgba(83,100,92,.28); }}
    .archive-control {{ display: inline-flex; align-items: center; gap: 7px; margin-top: 12px; color: var(--muted); font-size: 13px; }}
    .archive-control input {{ width: 16px; height: 16px; padding: 0; accent-color: var(--accent); }}
    .empty {{ grid-column: 1 / -1; padding: 34px; text-align: center; color: var(--muted); background: rgba(255,255,255,.74); border: 1px dashed var(--line); border-radius: 22px; }}
    @media (max-width: 860px) {{
      .hero, .search-row {{ grid-template-columns: 1fr; }}
      .meta {{ text-align: left; }}
      .stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .detail-grid {{ grid-template-columns: 1fr; }}
      .card summary {{ grid-template-columns: 1fr; }}
      .deadline {{ text-align: left; }}
      .card {{ grid-column: 1 / -1; }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header class="hero">
      <div>
        <h1>国际机会雷达</h1>
      </div>
      <div class="meta">{html.escape(generated_at)}</div>
    </header>

    <section class="stats" id="stats"></section>

    <section class="toolbar">
      <div class="search-row">
        <input id="search" type="search" placeholder="搜索标题、主办方、主题、材料或要求">
        <select id="sort">
          <option value="deadline">按截止时间</option>
          <option value="priority">按行动优先级</option>
          <option value="newest">按发现时间</option>
        </select>
        <select id="excluded">
          <option value="hide">隐藏排除项</option>
          <option value="show">显示排除项</option>
        </select>
        <select id="archiveView">
          <option value="active">未归档</option>
          <option value="archived">已归档</option>
          <option value="all">全部</option>
        </select>
      </div>
      <div class="filter-section">
        <div class="filter-label">机会类型</div>
        <div class="filters" id="typeFilters">{type_buttons}</div>
      </div>
      <div class="filter-section">
        <div class="filter-label">主题分区</div>
        <div class="filters" id="topicFilters">{topic_buttons}</div>
      </div>
    </section>

    <section class="content">
      <main class="list" id="list"></main>
    </section>
  </div>

  <script>
    const opportunities = {data_json};
    const initialStats = {stat_json};
    const archiveKey = "opportunityRadarArchived";
    const state = {{ type: "全部", topic: "全部", query: "", sort: "deadline", excluded: "hide", archiveView: "active" }};

    const statsEl = document.getElementById("stats");
    const listEl = document.getElementById("list");
    const searchEl = document.getElementById("search");
    const sortEl = document.getElementById("sort");
    const excludedEl = document.getElementById("excluded");
    const archiveViewEl = document.getElementById("archiveView");

    const priorityOrder = {{ "高": 0, "中高": 1, "中": 2, "低": 3 }};

    function escapeHtml(value) {{
      return String(value || "").replace(/[&<>"']/g, char => ({{
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }}[char]));
    }}

    function deadlineKey(row) {{
      const value = row["截止日期"] || "";
      return value && !value.includes("待核查") ? value.slice(0, 10) : "9999-99-99";
    }}

    function rowText(row) {{
      return Object.values(row).join(" ").toLowerCase();
    }}

    function rowId(row) {{
      return row["链接指纹"] || row["原网页链接"] || row["机会名称"];
    }}

    function archivedIds() {{
      try {{ return new Set(JSON.parse(localStorage.getItem(archiveKey) || "[]")); }}
      catch {{ return new Set(); }}
    }}

    function saveArchived(ids) {{
      localStorage.setItem(archiveKey, JSON.stringify([...ids]));
    }}

    function isArchived(row) {{
      return archivedIds().has(rowId(row));
    }}

    function setArchived(row, checked) {{
      const ids = archivedIds();
      const id = rowId(row);
      if (checked) ids.add(id);
      else ids.delete(id);
      saveArchived(ids);
      renderStats();
      renderList();
    }}

    function filteredRows() {{
      let rows = opportunities.filter(row => {{
        const archived = isArchived(row);
        if (state.archiveView === "active" && archived) return false;
        if (state.archiveView === "archived" && !archived) return false;
        if (state.excluded === "hide" && row["排除原因"]) return false;
        if (state.type !== "全部" && row["机会类型分组"] !== state.type) return false;
        if (state.topic !== "全部" && row["主题分区"] !== state.topic) return false;
        if (state.query && !rowText(row).includes(state.query.toLowerCase())) return false;
        return true;
      }});
      rows.sort((a, b) => {{
        if (state.sort === "priority") {{
          return (priorityOrder[a["行动优先级"]] ?? 9) - (priorityOrder[b["行动优先级"]] ?? 9);
        }}
        if (state.sort === "newest") {{
          return String(b["发现日期"] || "").localeCompare(String(a["发现日期"] || ""));
        }}
        return deadlineKey(a).localeCompare(deadlineKey(b));
      }});
      return rows;
    }}

    function renderStats() {{
      const activeCount = opportunities.filter(row => !row["排除原因"] && !isArchived(row)).length;
      const archivedCount = opportunities.filter(row => isArchived(row)).length;
      const items = [
        ["未归档", activeCount],
        ["今日新增", initialStats.today],
        ["近期截止", initialStats.soon],
        ["优先查看", initialStats.recommended],
        ["已归档", archivedCount],
      ];
      statsEl.innerHTML = items.map(([label, value]) => `<div class="stat"><strong>${{value}}</strong><span>${{label}}</span></div>`).join("");
    }}

    function field(label, value) {{
      return `<div class="field"><b>${{escapeHtml(label)}}</b><span>${{escapeHtml(value || "待核查")}}</span></div>`;
    }}

    function renderCard(row, index) {{
      const excludedClass = row["排除原因"] ? " excluded" : "";
      const applyLink = row["申请/投稿链接"] && row["申请/投稿链接"] !== "待核查"
        ? `<a href="${{escapeHtml(row["申请/投稿链接"])}}" target="_blank" rel="noreferrer">申请/投稿链接</a>` : "";
      const originalLink = row["原网页链接"]
        ? `<a href="${{escapeHtml(row["原网页链接"])}}" target="_blank" rel="noreferrer">原网页链接</a>` : "";
      const checked = isArchived(row) ? "checked" : "";
      return `
        <details class="card${{excludedClass}}">
          <summary>
            <div>
              <p class="title">${{escapeHtml(row["机会名称"])}}</p>
              <div class="chips">
                <span class="chip">${{escapeHtml(row["机会类型分组"])}}</span>
                <span class="chip topic">${{escapeHtml(row["主题分区"])}}</span>
                <span class="chip priority">优先级 ${{escapeHtml(row["行动优先级"])}}</span>
              </div>
            </div>
            <div class="deadline"><span>截止</span><strong>${{escapeHtml(row["截止日期"] || "待核查")}}</strong></div>
          </summary>
          <div class="details">
            <div class="detail-grid">
              ${{field("主办方", row["主办方"])}}
              ${{field("地点/形式", row["地点/线上"])}}
              ${{field("材料", row["需要准备的材料"])}}
              ${{field("要求", row["参加条件"])}}
              ${{field("岗位类型", row["岗位类型"])}}
              ${{field("岗位职能", row["岗位职能"])}}
              ${{field("排除原因", row["排除原因"] || "无")}}
              ${{field("状态", row["状态"])}}
            </div>
            <div class="judgment">
              <strong>备注与判断</strong><br>
              ${{escapeHtml(row["备注"] || "")}}
            </div>
            <div class="links">${{originalLink}} ${{applyLink}}</div>
            <label class="archive-control" onclick="event.stopPropagation()">
              <input type="checkbox" data-archive-id="${{escapeHtml(rowId(row))}}" ${{checked}}>
              已处理，不再显示
            </label>
          </div>
        </details>
      `;
    }}

    function renderList() {{
      const rows = filteredRows();
      if (!rows.length) {{
        listEl.innerHTML = '<div class="empty">当前筛选下没有机会。换一个类型、主题或搜索词试试。</div>';
        return;
      }}
      listEl.innerHTML = rows.map(renderCard).join("");
    }}

    function activateButtons(containerId, attr, value) {{
      document.querySelectorAll(`#${{containerId}} .filter-button`).forEach(button => {{
        button.classList.toggle("active", button.dataset[attr] === value);
      }});
    }}

    document.getElementById("typeFilters").addEventListener("click", event => {{
      if (!event.target.matches("button")) return;
      state.type = event.target.dataset.filterType;
      activateButtons("typeFilters", "filterType", state.type);
      renderList();
    }});
    document.getElementById("topicFilters").addEventListener("click", event => {{
      if (!event.target.matches("button")) return;
      state.topic = event.target.dataset.filterTopic;
      activateButtons("topicFilters", "filterTopic", state.topic);
      renderList();
    }});
    searchEl.addEventListener("input", () => {{ state.query = searchEl.value.trim(); renderList(); }});
    sortEl.addEventListener("change", () => {{ state.sort = sortEl.value; renderList(); }});
    excludedEl.addEventListener("change", () => {{ state.excluded = excludedEl.value; renderList(); }});
    archiveViewEl.addEventListener("change", () => {{ state.archiveView = archiveViewEl.value; renderList(); }});
    listEl.addEventListener("change", event => {{
      if (!event.target.matches("[data-archive-id]")) return;
      const id = event.target.dataset.archiveId;
      const row = opportunities.find(item => rowId(item) === id);
      if (row) setArchived(row, event.target.checked);
    }});

    renderStats();
    activateButtons("typeFilters", "filterType", "全部");
    activateButtons("topicFilters", "filterTopic", "全部");
    renderList();
  </script>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="04-数据库/机会数据库.csv")
    parser.add_argument("--output", default="docs/index.html")
    args = parser.parse_args()

    source = PROJECT_DIR / args.source
    output = PROJECT_DIR / args.output
    rows = normalize_rows(radar.load_csv(source, radar.FIELDS))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_dashboard(rows), encoding="utf-8")
    print(f"Generated {output.relative_to(PROJECT_DIR)} with {len(rows)} opportunities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
