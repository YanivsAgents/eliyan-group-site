"""Booking -> address+details to the GHL webhook. Widget completion messages are replayed from inside the real widget frame; webhook mocked."""
import asyncio, json, sys, os
from playwright.async_api import async_playwright
SP=os.environ.get("SHOTS", os.path.dirname(os.path.abspath(__file__)) + "/.shots"); os.makedirs(SP, exist_ok=True)
URL=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8766/index.html"
TAG=sys.argv[2] if len(sys.argv)>2 else "local"
results=[]
def ok(n,c,x=""): results.append((n,bool(c))); print(("PASS " if c else "FAIL ")+n+(" | "+x if x else ""))
STICKY=json.dumps({"first_name":"Test","last_name":"Booker","email":"test@example.com","phone":"+13055550100","appointment":{"start_time":"Thursday, Sep 24, 2026 05:30 PM","end_time":"Thursday, Sep 24, 2026 06:00 PM"}})
GATE={"fullName":"Test Booker","phone":"+13055550100","email":"test@example.com","street":"123 Palm Avenue","city":"Coral Gables","zip":"33134"}
async def gate(page, root):
    for k,v in GATE.items(): await page.fill(f"{root} .bkgate input[name={k}]", v)
    await page.click(f"{root} .bkgate button[type=submit]")
    await page.frame_locator(f"{root} iframe").locator("td.selectable.vdpCell").first.wait_for(timeout=30000)
async def fire(page, root):
    fr=await (await page.query_selector(f"{root} iframe")).content_frame()
    await fr.evaluate("(s)=>{window.parent.postMessage(['set-sticky-contacts','_ud',s,'RIFM68XCTV65yysAgYUh','fp123'],'*');window.parent.postMessage(['msgsndr-booking-complete',{fingerprint:'fp123',calendarId:'cal1'}],'*');}", STICKY)
    await page.wait_for_timeout(800)
def mocker(hits):
    async def mock(route,req): hits.append(json.loads(req.post_data or "{}")); await route.fulfill(status=200,body="{}",content_type="application/json")
    return mock
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); errors=[]
        for vp,mobile in (({"width":1440,"height":900},False),({"width":390,"height":844},True)):
            W=vp['width']
            ctx=await b.new_context(viewport=vp,is_mobile=mobile,has_touch=mobile,timezone_id="America/New_York")
            page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
            hits=[]; await page.route("**/services.leadconnectorhq.com/hooks/**",mocker(hits))
            await page.goto(URL,wait_until="load")
            await page.click(".mbar .mquote" if mobile else "a.navbook")
            await gate(page,"#bkmodal")
            g=hits[0] if hits else {}
            ok(f"[{W}] step 1 posts contact + address before the calendar (source website-booking-start)", len(hits)==1 and g.get("source")=="website-booking-start" and g.get("phone")=="+13055550100" and g.get("email")=="test@example.com" and g.get("street")=="123 Palm Avenue" and g.get("zip")=="33134", json.dumps(g)[:200])
            await page.evaluate("window.postMessage(['msgsndr-booking-complete',{}],'*')"); await page.wait_for_timeout(600)
            ok(f"[{W}] message NOT from widget iframe is ignored", await page.evaluate("document.querySelector('#bkmodal .bkflow').classList.contains('s-cal')"))
            await fire(page,"#bkmodal")
            ok(f"[{W}] booking-complete from widget shows Details step", await page.is_visible("#bkmodal .bkstep2") and await page.evaluate("document.querySelector('#bkmodal .bkflow').classList.contains('s-step2')"))
            ok(f"[{W}] calendar hidden in Details step", not await page.is_visible("#bkmodal .bkbody iframe"))
            ok(f"[{W}] contact fields hidden (prefilled from widget)", not await page.is_visible("#bkmodal .bkstep2 .contactrow"))
            ok(f"[{W}] address fields hidden (already collected)", not await page.is_visible("#bkmodal .bkstep2 .addrrow"))
            ok(f"[{W}] appointment time shown", "Sep 24, 2026 05:30 PM" in (await page.inner_text("#bkmodal .bkstep2 .bkwhen")))
            await page.screenshot(path=f"{SP}/{TAG}-step2-{W}.png")
            await page.click("#bkmodal .bkstep2 button[type=submit]"); await page.wait_for_timeout(300)
            ok(f"[{W}] empty Details blocked by validation", len(hits)==1)
            await page.select_option("#bkmodal .bkstep2 select[name=service]","Pool patio / pool deck")
            await page.select_option("#bkmodal .bkstep2 select[name=type]","Home")
            await page.select_option("#bkmodal .bkstep2 select[name=timeline]","As soon as possible")
            await page.fill("#bkmodal .bkstep2 textarea[name=details]","800 sq ft pool deck, travertine look")
            await page.check("#bkmodal .bkstep2 input[name=sms_consent]")
            await page.click("#bkmodal .bkstep2 button[type=submit]")
            await page.wait_for_selector("#bkmodal .bkstep2 .booked b:has-text('All set')",timeout=8000)
            d=hits[-1] if hits else {}
            ok(f"[{W}] details post has contact + address + details + appointment (2 posts total: step 1 + details)", len(hits)==2 and d.get("fullName")=="Test Booker" and d.get("email")=="test@example.com" and d.get("phone")=="+13055550100" and d.get("street")=="123 Palm Avenue" and d.get("city")=="Coral Gables" and d.get("state")=="FL" and d.get("zip")=="33134" and d.get("service")=="Pool patio / pool deck" and d.get("source")=="booking-step2" and d.get("appointment_start","").endswith("05:30 PM") and d.get("sms_consent")=="on", json.dumps(d)[:260])
            dl=await page.evaluate("window.dataLayer.map(e=>e.event).filter(Boolean)")
            ok(f"[{W}] GTM events book_address + booking_complete + form_submit", all(e in dl for e in ("book_address","booking_complete","form_submit")), str([e for e in dl if not e.startswith('gtm')]))
            await page.screenshot(path=f"{SP}/{TAG}-step2done-{W}.png")
            await page.click("#bkmodal .bkstep2 .js-done"); ok(f"[{W}] Done closes modal", not await page.is_visible("#bkmodal"))
            await page.click(".mbar .mquote" if mobile else "a.navbook")
            ok(f"[{W}] re-opening after a finished booking starts fresh at the address step", await page.is_visible("#bkmodal .bkgate") and (await page.input_value("#bkmodal .bkgate input[name=street]"))=="")
            await ctx.close()
        # --- SKIP path: booked, then "Skip for now" -> address still reaches GHL
        ctx=await b.new_context(viewport={"width":1440,"height":900},timezone_id="America/New_York"); page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
        hits=[]; await page.route("**/services.leadconnectorhq.com/hooks/**",mocker(hits))
        await page.goto(URL,wait_until="load"); await page.click("a.navbook"); await gate(page,"#bkmodal"); await fire(page,"#bkmodal")
        await page.click("#bkmodal .bkstep2 .js-skip"); await page.wait_for_timeout(800)
        d=hits[-1] if hits else {}
        ok("skip after booking still posts contact + address (source booking-address)", len(hits)==2 and d.get("source")=="booking-address" and d.get("street")=="123 Palm Avenue" and d.get("zip")=="33134" and d.get("fullName")=="Test Booker" and d.get("appointment_start","").endswith("05:30 PM"), json.dumps(d)[:220])
        ok("skip closes modal", not await page.is_visible("#bkmodal"))
        # --- CLOSE (X) path after booking, without touching Details -> address still posted, once
        hits.clear(); await page.click("a.navbook"); await gate(page,"#bkmodal"); await fire(page,"#bkmodal"); await page.click("#bkmodal .bkclose"); await page.wait_for_timeout(800)
        ok("closing the modal after booking posts the address once (after the step 1 post)", len(hits)==2 and hits[-1].get("source")=="booking-address", json.dumps(hits[-1])[:120] if hits else "no post")
        await page.click("a.navbook"); await page.wait_for_timeout(300)
        ok("re-opening after close-after-booking starts fresh at the address step", await page.is_visible("#bkmodal .bkgate"))
        await page.click("#bkmodal .bkclose"); await page.wait_for_timeout(500)
        ok("re-closing does not re-post", len(hits)==2)
        await ctx.close()
        # --- manual fallback: 'Already booked?' with no widget contact and no address -> both required
        ctx=await b.new_context(viewport={"width":1440,"height":900},timezone_id="America/New_York"); page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
        await page.goto(URL,wait_until="load"); await page.click("a.navbook"); await page.click(".bkfoot .later"); await page.wait_for_timeout(300)
        ok("manual 'Already booked?' shows contact + address fields, required", await page.is_visible("#bkmodal .bkstep2 .contactrow") and await page.is_visible("#bkmodal .bkstep2 .addrrow") and await page.evaluate("['phone','street','zip'].every(k=>document.querySelector('#bkmodal .bkstep2 [name='+k+']').required)"))
        await page.screenshot(path=f"{SP}/{TAG}-step2-manual.png")
        await ctx.close()
        # --- ON-PAGE section: same flow, Details shown inline in the section
        ctx=await b.new_context(viewport={"width":1440,"height":900},timezone_id="America/New_York"); page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
        hits=[]; await page.route("**/services.leadconnectorhq.com/hooks/**",mocker(hits))
        await page.goto(URL,wait_until="load"); await gate(page,"#booking"); await fire(page,"#booking")
        ok("section: booking-complete shows Details inside the section (modal stays closed)", await page.is_visible("#booking .bkstep2") and not await page.is_visible("#bkmodal"))
        await page.select_option("#booking .bkstep2 select[name=service]","Pavers"); await page.select_option("#booking .bkstep2 select[name=type]","Business")
        await page.click("#booking .bkstep2 button[type=submit]"); await page.wait_for_selector("#booking .bkstep2 .booked b:has-text('All set')",timeout=8000)
        d=hits[-1] if hits else {}
        ok("section: payload has address + details", d.get("street")=="123 Palm Avenue" and d.get("service")=="Pavers" and d.get("type")=="Business" and d.get("source")=="booking-step2", json.dumps(d)[:200])
        await page.evaluate("document.querySelector('#booking').scrollIntoView()"); await page.screenshot(path=f"{SP}/{TAG}-section-done.png")
        await page.click("#booking .bkstep2 .js-done"); await page.wait_for_timeout(300)
        ok("section: Done resets to the address step", await page.is_visible("#booking .bkgate"))
        await ctx.close()
        # --- PARTIAL CAPTURE (never lose a lead): typed-but-not-submitted contact reaches GHL
        ctx=await b.new_context(viewport={"width":1440,"height":900},timezone_id="America/New_York"); page=await ctx.new_page(); page.on("pageerror",lambda e:errors.append(str(e)))
        hits=[]; await page.route("**/services.leadconnectorhq.com/hooks/**",mocker(hits))
        await page.goto(URL,wait_until="load")
        await page.fill("#quote input[name=fullName]","Partial Person"); await page.fill("#quote input[name=phone]","305555"); await page.click("h1"); await page.wait_for_timeout(1500)
        ok("partial: no post while the phone is not reachable (fewer than 10 digits)", not hits)
        await page.fill("#quote input[name=phone]","(305) 555-0199"); await page.click("h1"); await page.wait_for_timeout(1500)
        d=hits[-1] if hits else {}
        ok("partial: leaving the quote form with a name + 10-digit phone posts a partial lead", len(hits)==1 and d.get("partial")=="true" and d.get("source")=="website-quote-form-partial" and d.get("fullName")=="Partial Person" and d.get("phone")=="(305) 555-0199" and d.get("page_url","").startswith("http"), json.dumps(d)[:200])
        await page.click("h1"); await page.wait_for_timeout(1500)
        ok("partial: leaving again without changes does not re-post", len(hits)==1)
        await page.fill("#quote input[name=email]","partial@example.com"); await page.select_option("#quote select[name=service]","Pavers"); await page.click("h1"); await page.wait_for_timeout(1500)
        d=hits[-1] if hits else {}
        ok("partial: new fields re-post the updated partial (email + service)", len(hits)==2 and d.get("email")=="partial@example.com" and d.get("service")=="Pavers" and d.get("partial")=="true", json.dumps(d)[:200])
        await page.select_option("#quote select[name=type]","Home")
        for k,v in (("street","123 Palm Avenue"),("city","Coral Gables"),("zip","33134")): await page.fill(f"#quote input[name={k}]",v)
        await page.click("#quote button[type=submit]"); await page.wait_for_selector("#quote .bkinline iframe",timeout=8000)
        d=hits[-1] if hits else {}
        ok("full submit posts the real lead (source website-quote-form, not partial)", len(hits)==3 and d.get("source")=="website-quote-form" and "partial" not in d and d.get("street")=="123 Palm Avenue" and d.get("email")=="partial@example.com", json.dumps(d)[:200])
        await page.click("h1"); await page.wait_for_timeout(1500)
        ok("no partial posts after the full submit", len(hits)==3)
        await page.click("a.navbook"); await page.fill("#bkmodal .bkgate input[name=fullName]","Gate Person"); await page.fill("#bkmodal .bkgate input[name=email]","gate@example.com"); await page.fill("#bkmodal .bkgate input[name=street]","9 Ocean Dr")
        await page.click("#bkmodal .bkclose"); await page.wait_for_timeout(1200)
        d=hits[-1] if hits else {}
        ok("closing the modal saves what was typed on step 1 (source website-booking-start-partial)", len(hits)==4 and d.get("source")=="website-booking-start-partial" and d.get("partial")=="true" and d.get("email")=="gate@example.com" and d.get("fullName")=="Gate Person" and d.get("street")=="9 Ocean Dr", json.dumps(d)[:200])
        await page.wait_for_timeout(1200); ok("modal close partial is posted once (flush + focusout dedupe)", len(hits)==4)
        await page.screenshot(path=f"{SP}/{TAG}-partial-quote.png")
        await ctx.close(); await b.close()
        ok("no JS errors", not errors, "; ".join(errors)[:200])
    f=[r for r in results if not r[1]]; print(f"\n{len(results)-len(f)}/{len(results)} passed"); sys.exit(1 if f else 0)
asyncio.run(main())
