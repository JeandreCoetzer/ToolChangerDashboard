"""Load the panel against mock_moonraker.py and take screenshots."""
import sys
from playwright.sync_api import sync_playwright

out = sys.argv[1] if len(sys.argv) > 1 else "."
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 640, "height": 760})
    pg.on("console", lambda m: m.type == "error" and errors.append(m.text))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto("http://127.0.0.1:8137/?moonraker=127.0.0.1:7125")
    pg.wait_for_selector(".tile.active", timeout=8000)
    pg.wait_for_timeout(1200)
    pg.screenshot(path=f"{out}/panel.png", full_page=True)
    assert pg.inner_text("#active-chip") == "T1 ACTIVE", pg.inner_text("#active-chip")
    n = pg.locator(".tile").count()
    print("tiles:", n)
    pg.click('.tile[data-tool="3"]')
    pg.wait_for_selector("#tool-dialog[open]")
    pg.wait_for_timeout(600)
    pg.screenshot(path=f"{out}/popup.png")
    pg.click("#td-select")
    pg.wait_for_function("document.querySelector('#active-chip').textContent === 'T3 ACTIVE'", timeout=5000)
    pg.click("#log-wrap summary")
    pg.wait_for_timeout(800)
    pg.screenshot(path=f"{out}/after_select.png", full_page=True)
    # settings round trip
    pg.click("#btn-settings"); pg.select_option("#sd-cols", "3"); pg.click("#sd-save")
    pg.wait_for_timeout(400)
    cols = pg.eval_on_selector("#grid", "e => getComputedStyle(e).getPropertyValue('--cols')")
    print("cols after settings:", cols)
    b.close()
print("console errors:", errors)
