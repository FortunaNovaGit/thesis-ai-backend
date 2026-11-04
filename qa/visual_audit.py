"""Explicit opt-in Playwright DOM/screenshot audit of actual preview URLs.

Run locally against WordPress staging. NEVER conflated with a passing synthetic
layout smoke: reports are tagged 'live-preview' or 'offline-fixture'.
No OpenAI calls, no site mutations and no auto-login or credential collection.
Install: pip install playwright && python -m playwright install chromium
Usage: python qa/visual_audit.py --url https://staging.example/page/ --output qa/evidence
Authenticated staging can use --storage-state <locally-generated Playwright state>.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import shutil
from urllib.parse import urlsplit, unquote

VIEWPORTS = {"desktop": (1440, 900), "tablet": (900, 800), "mobile": (390, 844), "small-mobile": (320, 740)}


async def inspect(url: str, output: pathlib.Path, storage_state: str | None = None) -> dict:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Install optional Playwright: pip install playwright && python -m playwright install chromium") from exc
    output.mkdir(parents=True, exist_ok=True)
    report = {"url": url, "kind": "offline-fixture" if urlsplit(url).scheme == "file" else "live-preview", "viewports": {}}
    async with async_playwright() as p:
        launch = {"headless": True}
        if shutil.which("chromium"):
            launch["executable_path"] = shutil.which("chromium")
        elif shutil.which("chromium-browser"):
            launch["executable_path"] = shutil.which("chromium-browser")
        browser = await p.chromium.launch(**launch)
        context_kwargs = {"storage_state": storage_state} if storage_state else {}
        context = await browser.new_context(**context_kwargs)
        for label, (width, height) in VIEWPORTS.items():
            page = await context.new_page()
            await page.set_viewport_size({"width": width, "height": height})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)[:240]))
            if urlsplit(url).scheme == "file":
                # Some managed Chromium distributions block file:// navigation;
                # set_content keeps the offline fixture completely local.
                local_path = pathlib.Path(unquote(urlsplit(url).path)).resolve()
                await page.set_content(local_path.read_text(encoding="utf-8"), wait_until="domcontentloaded")
                response = None
                status = 200
            else:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=20000)
                status = response.status if response else None
            await page.wait_for_timeout(300)
            measured = await page.evaluate("""() => {
                const d=document.documentElement;
                const all=[...document.querySelectorAll('img')];
                const h1=[...document.querySelectorAll('h1')].filter(x=>x.getClientRects().length);
                const badImages=all.filter(i=>i.getClientRects().length && (i.complete && i.naturalWidth===0));
                const noAlt=all.filter(i=>i.getClientRects().length && !i.hasAttribute('alt'));
                const buttons=[...document.querySelectorAll('a.elementor-button,button')].filter(x=>x.getClientRects().length);
                const aiSite=document.body.classList.contains('thesis-ai-generated');
                const sections=[...document.querySelectorAll('.elementor .thesis-ai-section')].filter(x=>x.getClientRects().length);
                const bounds=sections.map(x=>{const r=x.getBoundingClientRect();return {x:Math.round(r.x),width:Math.round(r.width)};});
                const visible=x=>!!x && getComputedStyle(x).display!=='none' && getComputedStyle(x).visibility!=='hidden' && !!x.getClientRects().length;
                const legacyPlaceholders=[...document.querySelectorAll('.tai-product-art,.tai-hero-art')].filter(visible).length;
                const themeTitles=[...document.querySelectorAll('.entry-header .entry-title,.page-header .entry-title')].filter(visible).length;
                return {title:document.title, viewport:window.innerWidth, scrollWidth:d.scrollWidth,
                    h1Count:h1.length, h1Text:h1.map(x=>x.innerText.slice(0,160)),
                    brokenImages:badImages.length, imagesWithoutAlt:noAlt.length,
                    visibleButtons:buttons.length, smallButtons:buttons.filter(b=>{const r=b.getBoundingClientRect();return r.width<40||r.height<40}).length,
                    aiOwned:aiSite, sectionBounds:bounds, legacyPlaceholderBlocks:legacyPlaceholders,
                    visibleThemeTitles:themeTitles};
            }""")
            measured["http_status"] = status
            measured["horizontal_overflow"] = measured["scrollWidth"] > measured["viewport"] + 3
            measured["page_errors"] = errors[:10]
            measured["narrow_sections"] = [b for b in measured["sectionBounds"] if
                                          b["width"] < measured["viewport"] * .90]
            measured["offscreen_sections"] = [b for b in measured["sectionBounds"] if
                                             b["x"] < -3 or b["x"] + b["width"] > measured["viewport"] + 3]
            measured["visual_defects"] = []
            if measured["aiOwned"] and measured["narrow_sections"]:
                measured["visual_defects"].append("narrow_ai_canvas")
            if measured["aiOwned"] and measured["offscreen_sections"]:
                measured["visual_defects"].append("offscreen_ai_section")
            if measured["aiOwned"] and measured["visibleThemeTitles"]:
                measured["visual_defects"].append("duplicate_theme_page_title")
            if measured["aiOwned"] and measured["legacyPlaceholderBlocks"]:
                measured["visual_defects"].append("large_decorative_placeholder")
            measured["passed_dom_smoke"] = (
                measured["http_status"] == 200 and not measured["horizontal_overflow"]
                and measured["h1Count"] == 1 and not errors and measured["brokenImages"] == 0
                and not measured["visual_defects"]
            )
            report["viewports"][label] = measured
            await page.screenshot(path=str(output / f"{label}.png"), full_page=True)
            await page.close()
        await browser.close()
    report["passed"] = all(item["passed_dom_smoke"] for item in report["viewports"].values())
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="One staging WordPress page URL; no external API calls beyond this page's assets")
    parser.add_argument("--output", default="qa/evidence")
    parser.add_argument("--storage-state", default=None)
    parser.add_argument("--allow-local-fixture", action="store_true", help="Permit file:// only for explicit offline test fixtures")
    args = parser.parse_args()
    scheme = urlsplit(args.url).scheme
    if scheme not in {"http", "https"} and not (args.allow_local_fixture and scheme == "file"):
        parser.error("URL must be http(s), or file:// with --allow-local-fixture")
    report = asyncio.run(inspect(args.url, pathlib.Path(args.output), args.storage_state))
    print(json.dumps({"passed": report["passed"], "kind": report["kind"], "evidence": str(args.output)}, ensure_ascii=False))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
