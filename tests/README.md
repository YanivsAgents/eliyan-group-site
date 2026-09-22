# Booking integration tests (Playwright, Python)

The site embeds the GoHighLevel booking calendar `pxL4fqAorvOoHVxhRaY9` in a three-step
flow: **1. jobsite address (required) -> 2. calendar -> 3. project details**. The flow is
mounted from `<template id="bkflow-tpl">` in two places: the modal (every `.js-book` CTA,
`/#book`, `/?book=1`) and the on-page `#booking` section. The hero quote form collects the
full address itself (street / city / state / zip, all required) and then shows the calendar
inline. The address is posted to the GHL webhook together with the booking: with the details
form (`source: booking-step2`), or on its own if the visitor skips or closes (`source:
booking-address`, one post per booking).

## Run

```bash
cd clients/jon-amram/website
python3 -m http.server 8766 --bind 127.0.0.1 --directory "$PWD" &
python3 tests/test_booking.py                      # real widget: gate, resize/scroll, click-through to 'Schedule meeting', quote form, section, mobile (36 checks)
python3 tests/test_step2.py                        # replayed widget messages: details step, payloads, skip/close, manual, section (34 checks)
python3 tests/test_booking.py https://www.eliyangroup.com/
python3 tests/test_step2.py   https://www.eliyangroup.com/ live
```

The GHL webhook is mocked in both suites and the widget's "Schedule meeting" button is never
clicked, so no leads or appointments are created. Screenshots land in `tests/.shots/`.

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
