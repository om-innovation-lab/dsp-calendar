"""Download the published Outlook calendar (ICS) and save upcoming events as data/events.json.

Runs inside GitHub Actions on a schedule. Expands recurring events and converts
all times to Oman time (Asia/Muscat).
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

ICS_URL = os.environ.get("ICS_URL", "").strip()
TZ = ZoneInfo("Asia/Muscat")
OUT = Path(__file__).resolve().parent.parent / "data" / "events.json"
PAST_DAYS = 120     # keep this many days of history
FUTURE_DAYS = 400   # and this far ahead


def to_local(value):
    """Return (iso_string, all_day) for an ICS date or datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=TZ)
        return value.astimezone(TZ).isoformat(timespec="minutes"), False
    return value.isoformat(), True


def main():
    if not ICS_URL:
        sys.exit("ICS_URL is not set")
    req = urllib.request.Request(ICS_URL, headers={"User-Agent": "directorate-calendar/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        raw = resp.read()

    cal = icalendar.Calendar.from_ical(raw)
    today = datetime.now(TZ).date()
    start = today - timedelta(days=PAST_DAYS)
    end = today + timedelta(days=FUTURE_DAYS)

    events = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        dtstart = ev.get("DTSTART").dt
        dtend_prop = ev.get("DTEND")
        dtend = dtend_prop.dt if dtend_prop else dtstart
        s, all_day = to_local(dtstart)
        e, _ = to_local(dtend)
        if all_day and isinstance(dtend, date) and not isinstance(dtend, datetime):
            # ICS all-day end is exclusive; store the last day instead
            e = (dtend - timedelta(days=1)).isoformat() if dtend > dtstart else s
        events.append({
            "title": str(ev.get("SUMMARY", "")).strip() or "(No title)",
            "start": s,
            "end": e,
            "allDay": all_day,
            "location": str(ev.get("LOCATION", "")).strip(),
            "description": str(ev.get("DESCRIPTION", "")).strip()[:1500],
        })

    events.sort(key=lambda x: (x["start"][:10], not x["allDay"], x["start"]))
    payload = {"events": events}

    old = None
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text(encoding="utf-8")).get("events")
        except Exception:
            old = None
    if old == events:
        print(f"No change ({len(events)} events)")
        return

    payload["updated"] = datetime.now(TZ).isoformat(timespec="minutes")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Saved {len(events)} events")


if __name__ == "__main__":
    main()
