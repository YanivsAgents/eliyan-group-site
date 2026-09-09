# Booking integration tests (Playwright, Python)

The site embeds the GoHighLevel booking calendar `pxL4fqAorvOoHVxhRaY9` in a modal
(opened by every `.js-book` CTA and by `/#book` or `/?book=1`) and, after the
quote form, inline in the hero card. After a booking completes, the modal shows a
Step 2 project-details form that posts to the same GHL webhook.

## Run

```bash
cd clients/jon-amram/website
python3 -m http.server 8766 --bind 127.0.0.1 --directory "$PWD" &
python3 tests/test_booking.py                      # CTAs, modal, deep link, form -> calendar (22 checks)
python3 tests/test_step2.py                        # booking -> Step 2 form -> webhook (20 checks)
python3 tests/test_booking.py https://www.eliyangroup.com/
python3 tests/test_step2.py   https://www.eliyangroup.com/ live
```

The GHL webhook is mocked in both suites; no leads or appointments are created.
Screenshots land in `tests/.shots/`.

## How booking completion is detected

The GHL widget (chunk `BUO9Gj7W.js`) posts to the parent, in this order:

1. `["set-sticky-contacts", "_ud", "<json>", locationId, fingerprint]` where the JSON
   holds the contact (`first_name`, `last_name`, `email`, `phone`) plus
   `appointment.start_time` / `end_time` as formatted strings.
2. `["msgsndr-booking-complete", {fingerprint, calendarId}]`

`index.html` accepts these only when `event.source` is the modal iframe's window.
