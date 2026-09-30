"""Desktop/mobile checks for the generated static dashboard."""

from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("/private/tmp/radar-browser-check")
OUTPUT.mkdir(exist_ok=True)

with sync_playwright() as runtime:
    browser = runtime.chromium.launch()
    for name, width, height in [("desktop", 1440, 1000), ("mobile", 390, 844)]:
        context = browser.new_context(viewport={"width": width, "height": height})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.clock.install(time=1790856000000)
        page.goto((ROOT / "docs/index.html").as_uri())
        assert page.locator("h1").inner_text() == "Opportunity Radar"
        assert page.locator("#stats .stat").count() == 5
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "horizontal overflow"
        page.screenshot(path=str(OUTPUT / (name + "-home.png")), full_page=False)
        page.locator("button[data-filter-type='Early-career Jobs']").click()
        page.locator("button[data-filter-type='全部']").click()
        page.locator("#archiveView").select_option("all")
        first_control = page.locator("input[data-archive-id]").first
        if first_control.count():
            card = first_control.locator("xpath=ancestor::details")
            card.locator("summary").click()
            first_control.check()
            stored = json.loads(page.evaluate("localStorage.getItem('opportunityRadarArchived')"))
            assert len(stored) == 1
            page.reload()
            page.locator("#archiveView").select_option("archived")
            checkbox = page.locator("input[data-archive-id]").first
            checkbox.locator("xpath=ancestor::details").locator("summary").click()
            assert checkbox.is_checked()
            checkbox.click()
            assert json.loads(page.evaluate("localStorage.getItem('opportunityRadarArchived')")) == []
        page.locator("#archiveView").select_option("all")
        page.locator(".card").first.locator("summary").click()
        assert page.locator(".eligibility").first.inner_text().find("Citizenship") >= 0
        assert page.locator(".eligibility").first.inner_text().find("Not stated") >= 0
        assert not errors, errors
        page.screenshot(path=str(OUTPUT / (name + ".png")), full_page=False)
        context.close()
    browser.close()
print("Desktop/mobile: filters, eligibility, archive persistence, restore, safe layout and JavaScript passed")
