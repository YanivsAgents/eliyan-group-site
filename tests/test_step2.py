import asyncio, json, sys
from playwright.async_api import async_playwright
import os; SP=os.environ.get("SHOTS", os.path.dirname(os.path.abspath(__file__)) + "/.shots"); os.makedirs(SP, exist_ok=True)
URL=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8766/index.html"
TAG=sys.argv[2] if len(sys.argv)>2 else "local"
results=[]
def ok(n,c,x=""): results.append((n,bool(c))); print(("PASS " if c else "FAIL ")+n+(" | "+x if x else ""))
STICKY=json.dumps({"first_name":"Test","last_name":"Booker","email":"test@example.com","phone":"+13055550100","appointment":{"start_time":"Thursday, Sep 10, 2026 05:30 PM","end_time":"Thursday, Sep 10, 2026 06:00 PM"}})
async def fire(page):
    fr=page.frame(url=lambda u: "widget/booking" in u)
    await fr.evaluate("(s)=>{window.parent.postMessage(['set-sticky-contacts','_ud',s,'RIFM68XCTV65yysAgYUh','fp123'],'*');window.parent.postMessage(['msgsndr-booking-complete',{fingerprint:'fp123',calendarId:'cal1'}],'*');}", STICKY)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); errors=[]
        for vp,mobile in (({"width":1440,"height":900},False),({"width":390,"height":844},True)):
            ctx=await b.new_context(viewport=vp,is_mobile=mobile,has_touch=mobile,timezone_id="America/New_York")
            page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
            hits=[]
            async def mock(route,req): hits.append(json.loads(req.post_data or "{}")); await route.fulfill(status=200,body="{}",content_type="application/json")
            await page.route("**/services.leadconnectorhq.com/hooks/**",mock)
            await page.goto(URL,wait_until="networkidle")
            await page.click(".mbar .mquote" if mobile else "a.navbook")
            await page.frame_locator("#bkmodal iframe").locator("button,[role=button],td").first.wait_for(timeout=25000)
            # --- untrusted message from the page itself must be ignored
            await page.evaluate("window.postMessage(['msgsndr-booking-complete',{}],'*')"); await page.wait_for_timeout(600)
            ok(f"[{vp['width']}] message NOT from widget iframe is ignored", not await page.evaluate("document.querySelector('.bkbox').classList.contains('step2')"))
            # --- real widget messages
            await fire(page); await page.wait_for_timeout(800)
            ok(f"[{vp['width']}] booking-complete from widget shows Step 2", await page.is_visible("#bkstep2"))
            ok(f"[{vp['width']}] calendar hidden in Step 2", not await page.is_visible("#bkmodal .bkbody iframe"))
            ok(f"[{vp['width']}] contact fields hidden (prefilled from widget)", not await page.is_visible("#bkstep2 .contactrow"))
            ok(f"[{vp['width']}] appointment time shown", "Sep 10, 2026 05:30 PM" in (await page.inner_text("#bkwhen")))
            await page.screenshot(path=f"{SP}/{TAG}-step2-{vp['width']}.png")
            # required validation blocks empty submit
            await page.click("#bkstep2 button[type=submit]"); await page.wait_for_timeout(300)
            ok(f"[{vp['width']}] empty Step 2 blocked by validation", not hits)
            await page.select_option("#bkstep2 select[name=service]","Pool patio / pool deck")
            await page.select_option("#bkstep2 select[name=type]","Home")
            await page.select_option("#bkstep2 select[name=city]","Pinecrest")
            await page.fill("#bkstep2 input[name=zip]","33156")
            await page.select_option("#bkstep2 select[name=timeline]","As soon as possible")
            await page.fill("#bkstep2 textarea[name=details]","800 sq ft pool deck, travertine look")
            await page.check("#bksmsc")
            await page.click("#bkstep2 button[type=submit]")
            await page.wait_for_selector("#bkstep2 .booked b:has-text('All set')",timeout=8000)
            d=hits[0] if hits else {}
            ok(f"[{vp['width']}] webhook got merged payload", d.get("fullName")=="Test Booker" and d.get("email")=="test@example.com" and d.get("phone")=="+13055550100" and d.get("service")=="Pool patio / pool deck" and d.get("zip")=="33156" and d.get("source")=="booking-step2" and d.get("appointment_start","").endswith("05:30 PM") and d.get("sms_consent")=="on", json.dumps(d)[:220])
            dl=await page.evaluate("window.dataLayer.map(e=>e.event).filter(Boolean)")
            ok(f"[{vp['width']}] GTM events booking_complete + form_submit", "booking_complete" in dl and "form_submit" in dl, str([e for e in dl if not e.startswith('gtm')]))
            await page.screenshot(path=f"{SP}/{TAG}-step2done-{vp['width']}.png")
            await page.click("#bkstep2 .btn"); ok(f"[{vp['width']}] Done closes modal", not await page.is_visible("#bkmodal"))
            await ctx.close()
        # --- manual fallback: 'Already booked?' with no widget contact -> contact fields required
        ctx=await b.new_context(viewport={"width":1440,"height":900}); page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
        await page.goto(URL,wait_until="networkidle"); await page.click("a.navbook"); await page.click(".bkfoot .later"); await page.wait_for_timeout(300)
        ok("manual 'Already booked?' shows Step 2 with contact fields", await page.is_visible("#bkstep2 .contactrow") and await page.evaluate("document.querySelector('#bkstep2 [name=phone]').required"))
        await page.screenshot(path=f"{SP}/{TAG}-step2-manual.png")
        await ctx.close(); await b.close()
        ok("no JS errors", not errors, "; ".join(errors)[:200])
    f=[r for r in results if not r[1]]; print(f"\n{len(results)-len(f)}/{len(results)} passed"); sys.exit(1 if f else 0)
asyncio.run(main())
