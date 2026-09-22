"""Booking flow against the REAL GHL widget (no appointment is ever submitted; the webhook is mocked)."""
import asyncio, json, sys, os
from playwright.async_api import async_playwright
SP=os.environ.get("SHOTS", os.path.dirname(os.path.abspath(__file__)) + "/.shots"); os.makedirs(SP, exist_ok=True)
URL=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8766/index.html"
WIDGET="pxL4fqAorvOoHVxhRaY9"
results=[]
def ok(name,cond,extra=""): results.append((name,bool(cond),extra)); print(("PASS " if cond else "FAIL ")+name+(" | "+extra if extra else ""))
ADDR={"street":"123 Palm Avenue","city":"Coral Gables","zip":"33134"}

async def fill_gate(page, root):
    for k,v in ADDR.items(): await page.fill(f"{root} .bkgate input[name={k}]", v)
    await page.click(f"{root} .bkgate button[type=submit]")

async def widget_ready(page, root):
    await page.frame_locator(f"{root} iframe").locator("td.selectable.vdpCell").first.wait_for(timeout=30000)
    await page.wait_for_timeout(2000)

async def iframe_h(page, sel): return await page.evaluate(f"Math.round(document.querySelector('{sel}').getBoundingClientRect().height)")

async def walk_to_confirm(page, root, vp_h, tag):
    """day -> slot -> Select -> contact form; assert 'Schedule meeting' can be scrolled into view. Never clicks it."""
    fr=await (await page.query_selector(f"{root} iframe")).content_frame()
    await fr.locator("td.selectable.vdpCell").nth(1).click(); await page.wait_for_timeout(1200)
    await fr.locator("li.widgets-time-slot").first.click(); await page.wait_for_timeout(1000)
    await fr.locator("button.selected-slot").first.click(); await page.wait_for_timeout(2500)
    h=await iframe_h(page, f"{root} iframe")
    btn=fr.locator("button:has-text('Schedule meeting')").last
    ok(f"[{tag}] widget reached its contact-form step", await btn.count()==1)
    await btn.scroll_into_view_if_needed(); await page.wait_for_timeout(300)
    bb=await btn.bounding_box()
    vis=bool(bb) and bb["y"]>=0 and bb["y"]+bb["height"]<=vp_h
    ok(f"[{tag}] 'Schedule meeting' button fully visible after scrolling", vis, f"iframe {h}px, button y={bb['y']:.0f}..{bb['y']+bb['height']:.0f} of {vp_h}" if bb else "no box")
    await page.screenshot(path=f"{SP}/{tag}-confirm-reachable.png")

async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); errors=[]
        # ---------- DESKTOP ----------
        ctx=await b.new_context(viewport={"width":1440,"height":900}, timezone_id="America/New_York")
        page=await ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        hits=[]
        async def mock(route, req):
            hits.append(json.loads(req.post_data or "{}")); await route.fulfill(status=200, body='{"ok":true}', content_type="application/json")
        await page.route("**/services.leadconnectorhq.com/hooks/**", mock)
        await page.goto(URL, wait_until="load")
        ok("embed script loaded", await page.evaluate("!!Array.from(document.scripts).find(s=>s.src.includes('form_embed.js'))"))
        ok("modal hidden on load", not await page.is_visible("#bkmodal"))
        await page.click("a.navbook")
        ok("nav Book Online opens modal on the ADDRESS step", await page.is_visible("#bkmodal .bkgate") and await page.evaluate("document.querySelector('#bkmodal .bkflow').classList.contains('s-gate')"))
        ok("calendar iframe not loaded before the address is given", (await page.get_attribute("#bkmodal iframe","src")) in (None,""))
        await page.screenshot(path=f"{SP}/t1-desktop-gate.png")
        await page.click("#bkmodal .bkgate button[type=submit]"); await page.wait_for_timeout(200)
        ok("empty address blocked (still on address step)", await page.evaluate("document.querySelector('#bkmodal .bkflow').classList.contains('s-gate')"))
        await page.fill("#bkmodal .bkgate input[name=street]","123 Palm Avenue"); await page.fill("#bkmodal .bkgate input[name=city]","Coral Gables")
        await page.click("#bkmodal .bkgate button[type=submit]"); await page.wait_for_timeout(200)
        ok("missing zip blocked", await page.evaluate("document.querySelector('#bkmodal .bkflow').classList.contains('s-gate')"))
        await page.fill("#bkmodal .bkgate input[name=zip]","33134"); await page.click("#bkmodal .bkgate button[type=submit]")
        ok("full address -> calendar step", await page.evaluate("document.querySelector('#bkmodal .bkflow').classList.contains('s-cal')"))
        src=await page.get_attribute("#bkmodal iframe","src"); ok("iframe src set to GHL widget", src and WIDGET in src, src)
        await widget_ready(page,"#bkmodal")
        h=await iframe_h(page,"#bkmodal iframe")
        ok("iframe resized to widget content (was stuck at 640)", h>800, f"{h}px")
        sc=await page.evaluate("(()=>{const h=document.querySelector('#bkmodal .bkflowhost');return [h.scrollHeight,h.clientHeight]})()")
        ok("modal body scrolls when the widget is taller than the viewport", sc[0]>sc[1], f"scroll {sc[0]} > client {sc[1]}")
        ok("iframe is NOT scrolling=no", (await page.get_attribute("#bkmodal iframe","scrolling")) != "no")
        await page.screenshot(path=f"{SP}/t1-desktop-calendar.png")
        await walk_to_confirm(page,"#bkmodal",900,"desktop")
        await page.click("#bkmodal .bkclose")
        ok("X closes modal", not await page.is_visible("#bkmodal"))
        ok("body scroll unlocked after close", not await page.evaluate("document.body.classList.contains('bklock')"))
        await page.click("section.final a.js-book"); ok("final-section CTA opens modal", await page.is_visible("#bkmodal"))
        await page.mouse.click(10,10); ok("overlay click closes modal", not await page.is_visible("#bkmodal"))
        await page.goto(URL+"#book", wait_until="load"); await page.wait_for_timeout(500)
        ok("deep link #book (hash change) opens modal", await page.is_visible("#bkmodal"))
        await page.click("#bkmodal .bkclose")
        pg2=await ctx.new_page(); await pg2.goto(URL+"?book=1", wait_until="load"); await pg2.wait_for_timeout(600)
        ok("fresh load with ?book=1 opens modal at the address step", await pg2.is_visible("#bkmodal .bkgate")); await pg2.close()
        # ---------- ON-PAGE SECTION ----------
        await page.goto(URL, wait_until="load")
        ok("on-page #booking section exists with address step", await page.is_visible("#booking .bkgate"))
        await page.evaluate("document.querySelector('#booking').scrollIntoView()"); await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SP}/t3-desktop-section-gate.png")
        await fill_gate(page,"#booking")
        ok("section: address -> calendar", await page.evaluate("document.querySelector('#booking .bkflow').classList.contains('s-cal')"))
        await widget_ready(page,"#booking")
        h=await iframe_h(page,"#booking iframe"); ok("section calendar resized to content", h>800, f"{h}px")
        await page.evaluate("document.querySelector('#booking').scrollIntoView()"); await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SP}/t3-desktop-section-calendar.png")
        # ---------- QUOTE FORM (address split + required) ----------
        await page.goto(URL, wait_until="load")
        names=await page.evaluate("Array.from(document.querySelectorAll('#quote [name]')).map(i=>i.name)")
        ok("quote form has street/city/state/zip", all(k in names for k in ("street","city","state","zip")), str(names))
        ok("quote address fields are required", await page.evaluate("['street','city','state','zip'].every(k=>document.querySelector('#quote [name='+k+']').required)"))
        await page.fill("#quote input[name=fullName]","Test Booking Flow"); await page.fill("#quote input[name=phone]","(305) 555-0100"); await page.fill("#quote input[name=email]","test@example.com")
        await page.select_option("#quote select[name=service]","Pavers"); await page.select_option("#quote select[name=type]","Home")
        await page.fill("#quote input[name=city]","Coral Gables"); await page.fill("#quote input[name=zip]","33134")
        await page.click("#quote button[type=submit]"); await page.wait_for_timeout(300)
        ok("quote submit blocked without street", not hits and await page.is_visible("#quote input[name=street]"))
        await page.fill("#quote input[name=street]","123 Palm Avenue")
        await page.screenshot(path=f"{SP}/t2-desktop-quote-filled.png")
        await page.click("#quote button[type=submit]")
        await page.wait_for_selector("#quote .bkinline iframe", timeout=8000)
        d=hits[0] if hits else {}
        ok("webhook payload has split address", d.get("street")=="123 Palm Avenue" and d.get("city")=="Coral Gables" and d.get("state")=="FL" and d.get("zip")=="33134" and d.get("fullName")=="Test Booking Flow", json.dumps(d)[:200])
        isrc=await page.get_attribute("#quote .bkinline iframe","src")
        ok("inline calendar prefilled from form", isrc and all(k in isrc for k in ("first_name=Test","last_name=Booking+Flow","email=test%40example.com","phone=")), isrc)
        await widget_ready(page,"#quote .bkinline"); h=await iframe_h(page,"#quote .bkinline iframe")
        ok("inline calendar resized to content (narrow card layout)", h>700, f"{h}px")
        await page.screenshot(path=f"{SP}/t2-desktop-after-submit.png")
        dl=await page.evaluate("window.dataLayer.map(e=>e.event).filter(Boolean)")
        ok("GTM dataLayer events pushed", "form_submit" in dl and "book_open" in dl, str(dl))
        await ctx.close()
        # ---------- MOBILE ----------
        ctx=await b.new_context(viewport={"width":390,"height":844}, is_mobile=True, has_touch=True, timezone_id="America/New_York")
        page=await ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL, wait_until="load")
        await page.click(".mbar .mquote")
        ok("[mobile] sticky bar opens modal at address step", await page.is_visible("#bkmodal .bkgate"))
        await page.screenshot(path=f"{SP}/t4-mobile-gate.png")
        await fill_gate(page,"#bkmodal"); await widget_ready(page,"#bkmodal")
        h=await iframe_h(page,"#bkmodal iframe"); ok("[mobile] calendar iframe resized", h>700, f"{h}px")
        await page.screenshot(path=f"{SP}/t4-mobile-calendar.png")
        await walk_to_confirm(page,"#bkmodal",844,"mobile")
        h2=await iframe_h(page,"#bkmodal iframe"); ok("[mobile] iframe grew for the contact-form step", h2>h, f"{h}px -> {h2}px")
        await page.click("#bkmodal .bkclose"); ok("[mobile] X closes modal", not await page.is_visible("#bkmodal"))
        await page.evaluate("document.querySelector('#booking').scrollIntoView()"); await page.wait_for_timeout(300)
        await page.screenshot(path=f"{SP}/t4-mobile-section.png")
        await ctx.close(); await b.close()
        ok("no JS errors", not errors, "; ".join(errors)[:200])
    f=[r for r in results if not r[1]]; print(f"\n{len(results)-len(f)}/{len(results)} passed"); sys.exit(1 if f else 0)
asyncio.run(main())
