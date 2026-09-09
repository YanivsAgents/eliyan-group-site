import asyncio, json, sys
from playwright.async_api import async_playwright
import os; SP=os.environ.get("SHOTS", os.path.dirname(os.path.abspath(__file__)) + "/.shots"); os.makedirs(SP, exist_ok=True)
URL=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8766/index.html"
WIDGET="pxL4fqAorvOoHVxhRaY9"
results=[]; 
def ok(name,cond,extra=""): results.append((name,bool(cond),extra)); print(("PASS " if cond else "FAIL ")+name+(" | "+extra if extra else ""))

async def wait_calendar(page, frame_sel, timeout=25000):
    """wait until the GHL widget iframe has rendered real calendar UI"""
    fl=page.frame_locator(frame_sel)
    # GHL booking widget renders a month grid; wait for any button/day cell to be visible
    await fl.locator("button, [role=button], .day, td").first.wait_for(state="visible", timeout=timeout)
    txt=await fl.locator("body").inner_text()
    return txt

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        errors=[]
        # ---------- DESKTOP ----------
        ctx=await b.new_context(viewport={"width":1440,"height":900}, timezone_id="America/New_York")
        page=await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type=="error" else None)
        await page.goto(URL, wait_until="networkidle")
        ok("embed script loaded", await page.evaluate("!!Array.from(document.scripts).find(s=>s.src.includes('form_embed.js'))"))
        ok("modal hidden on load", not await page.is_visible("#bkmodal"))
        ok("iframe src NOT set before open (lazy)", (await page.get_attribute("#bkmodal iframe","src")) in (None,""))
        # nav CTA
        await page.click("a.navbook")
        ok("nav Book Online opens modal", await page.is_visible("#bkmodal"))
        src=await page.get_attribute("#bkmodal iframe","src")
        ok("iframe src set to GHL widget", src and WIDGET in src, src)
        txt=await wait_calendar(page, "#bkmodal iframe")
        ok("calendar UI rendered inside iframe", len(txt.strip())>20, txt.strip().replace("\n"," | ")[:160])
        await page.wait_for_timeout(1500)
        h=await page.evaluate("document.querySelector('#bkmodal iframe').getBoundingClientRect().height")
        ok("iframe has real height", h>=400, f"{h:.0f}px")
        await page.screenshot(path=f"{SP}/t1-desktop-modal.png")
        await page.keyboard.press("Escape")
        ok("Escape closes modal", not await page.is_visible("#bkmodal"))
        # final CTA + overlay click close
        await page.click("section.final a.js-book")
        ok("final-section CTA opens modal", await page.is_visible("#bkmodal"))
        await page.mouse.click(10,10)
        ok("overlay click closes modal", not await page.is_visible("#bkmodal"))
        ok("body scroll unlocked after close", not await page.evaluate("document.body.classList.contains('bklock')"))
        # deep link
        await page.goto(URL+"#book", wait_until="load")
        await page.wait_for_timeout(500)
        ok("deep link #book auto-opens modal", await page.is_visible("#bkmodal"))
        await page.keyboard.press("Escape")
        # ---------- FORM -> CALENDAR (webhook mocked, no real lead created) ----------
        hits=[]
        async def mock(route, req):
            hits.append(json.loads(req.post_data or "{}")); await route.fulfill(status=200, body='{"ok":true}', content_type="application/json")
        await page.route("**/services.leadconnectorhq.com/hooks/**", mock)
        await page.goto(URL, wait_until="networkidle")
        await page.fill("#quote input[name=fullName]","Test Booking Flow")
        await page.fill("#quote input[name=phone]","(305) 555-0100")
        await page.fill("#quote input[name=email]","test@example.com")
        await page.select_option("#quote select[name=service]","Pavers")
        await page.select_option("#quote select[name=type]","Home")
        await page.select_option("#quote select[name=city]","Coral Gables")
        await page.fill("#quote input[name=zip]","33134")
        await page.click("#quote button[type=submit]")
        await page.wait_for_selector("#quote .bkinline iframe", timeout=8000)
        ok("webhook received lead payload (mocked)", hits and hits[0].get("fullName")=="Test Booking Flow", json.dumps(hits[0])[:140] if hits else "")
        isrc=await page.get_attribute("#quote .bkinline iframe","src")
        ok("inline calendar shown after submit", isrc and WIDGET in isrc)
        ok("calendar prefilled from form", all(k in (isrc or "") for k in ("first_name=Test","last_name=Booking+Flow","email=test%40example.com","phone=")), isrc)
        txt=await wait_calendar(page, "#quote .bkinline iframe")
        ok("inline calendar UI rendered", len(txt.strip())>20)
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SP}/t2-desktop-after-submit.png")
        # dataLayer events
        dl=await page.evaluate("window.dataLayer.map(e=>e.event).filter(Boolean)")
        ok("GTM dataLayer events pushed", "form_submit" in dl and "book_open" in dl, str(dl))
        await ctx.close()
        # ---------- MOBILE ----------
        ctx=await b.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True, device_scale_factor=2)
        page=await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL, wait_until="networkidle")
        ok("mobile sticky bar visible", await page.is_visible(".mbar"))
        await page.click(".mbar .mquote")
        ok("mobile bar Book a Time opens modal", await page.is_visible("#bkmodal"))
        await wait_calendar(page, "#bkmodal iframe")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{SP}/t3-mobile-modal.png")
        await page.keyboard.press("Escape")
        await page.click(".burger"); await page.wait_for_timeout(300)
        await page.click(".mobilemenu .mmbook")
        ok("mobile menu Book link opens modal", await page.is_visible("#bkmodal"))
        ok("mobile menu closed after tap", not await page.evaluate("document.getElementById('mm').classList.contains('open')"))
        await ctx.close(); await b.close()
        real=[e for e in errors if "favicon" not in e and "googletagmanager" not in e]
        ok("no page JS errors", not [e for e in errors if "ReferenceError" in e or "TypeError" in e or "SyntaxError" in e], "; ".join(real)[:300])
    fails=[r for r in results if not r[1]]
    print(f"\n{len(results)-len(fails)}/{len(results)} passed")
    sys.exit(1 if fails else 0)
asyncio.run(main())
