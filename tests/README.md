# Booking integration tests (Playwright, Python)

The site embeds the GoHighLevel booking calendar `pxL4fqAorvOoHVxhRaY9` in a three-step
flow: **1. your info + jobsite address (all required) -> 2. calendar -> 3. project details**. The
flow is mounted from `<template id="bkflow-tpl">` in two places: the modal (every `.js-book` CTA,
`/#book`, `/?book=1`) and the on-page `#booking` section. The hero quote form collects contact +
full address itself and then shows the calendar inline.

## When a lead reaches the GHL webhook ("never lose a lead", 2026-09-30)

Every post carries `source` and `page_url`. GHL upserts by email/phone, so one visitor can post
several times and lands on one contact.

| Moment | `source` | Extra keys |
|---|---|---|
| Hero quote form submitted | `website-quote-form` | all form fields |
| Booking step 1 "Continue to pick a time" | `website-booking-start` | fullName, phone, email, street, city, state, zip |
| Details form after a booking | `booking-step2` | + service, type, timeline, details, sms_consent, appointment_start/end |
| Booked, then "Skip" or close without details | `booking-address` | contact + address + appointment_start/end |
| **Typed but never submitted** (hero form or step 1) | `website-quote-form-partial` / `website-booking-start-partial` | `partial:"true"` + whatever was filled |

Partial capture (`bkPartial()` in index.html) arms once the form holds a 10-digit phone or an
email. It posts 20 s after the last keystroke, when focus leaves the form, when the modal closes,
and on `pagehide` / tab hidden (keepalive). It re-posts only when the content changed and stops
for good once the form is really submitted. Disclosed in `/privacy` §01.

## Run

```bash
cd clients/jon-amram/website
python3 -m http.server 8766 --bind 127.0.0.1 --directory "$PWD" &
python3 tests/test_booking.py                      # real widget: step 1 (contact+address, posts, prefill), resize/scroll, click-through to 'Schedule meeting', quote form, section, mobile
python3 tests/test_step2.py                        # replayed widget messages: step-1 post, details step, payloads, skip/close, manual, section, partial capture
python3 tests/test_booking.py https://www.eliyangroup.com/
python3 tests/test_step2.py   https://www.eliyangroup.com/ live
```

The GHL webhook is mocked in both suites and the widget's "Schedule meeting" button is never
clicked, so no leads or appointments are created. Screenshots land in `tests/.shots/`.

**Month-end note (2026-09-30):** `walk_to_confirm()` clicks the second open day in the widget's
current month view. When fewer than two days are open (e.g. the last day of a month) it first
clicks the widget's `button.arrowNext` to move to the next month, so the suite stays green
year-round.

## Iframe sizing (the "can't scroll to confirm" bug, fixed 2026-09-22)

The widget posts `["highlevel.setHeight",{height}]` but `form_embed.js` only sizes iframes that
had a `src` at page load, so a lazily-loaded iframe stayed at its 640px min-height with
`scrolling="no"` and the bottom of the widget (slot "Select", "Schedule meeting") was cut off.
Now `bkWatch()` initialises `window.iFrameResize` (bundled in `form_embed.js`; the widget is an
iframe-resizer child) on every calendar iframe, so the height follows each step, and
`bkResize()` uses the widget's own `setHeight` as a `min-height` floor (or as the height if
iFrameResize is missing). The iframe is never `scrolling="no"`, so it can still scroll inside
as a last resort. The modal's scroll container is `.bkbox .bkflowhost`.

## How booking completion is detected

The GHL widget (chunk `BUO9Gj7W.js`) posts to the parent, in this order:

1. `["set-sticky-contacts", "_ud", "<json>", locationId, fingerprint]` where the JSON
   holds the contact (`first_name`, `last_name`, `email`, `phone`) plus
   `appointment.start_time` / `end_time` as formatted strings.
2. `["msgsndr-booking-complete", {fingerprint, calendarId}]`

`index.html` accepts these only when `event.source` is the modal iframe's window.
