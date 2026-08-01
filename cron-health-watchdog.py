#!/usr/bin/env python3
"""
Cron Health Watchdog (runs hourly from cron)

The collector can fail silently: if the PVS6 stops answering, every cron run
logs an error and no data lands, but nothing tells anyone. This script checks
that data is actually flowing and emails SUPERVISOR_EMAIL when it is not:

  * overview.csv must have a row no older than ~50 minutes behind the most
    recent scheduled collection run (every 15 min, 4 AM - 11:45 PM)
  * daily_summary.csv must have yesterday's row once the 5 AM summary has run

Sends one alert email when a problem appears, then reminders with exponential
backoff while it persists (1 day, 2 days, 4 days, ... capped at weekly), and a
recovery email when data flows again. Alert state is kept in
output/.watchdog_state.json.

Usage:
    python cron-health-watchdog.py          # normal check (for cron)
    python cron-health-watchdog.py --test   # send a test email and exit
"""

import csv
import json
import smtplib
import sys
from collections import deque
from datetime import datetime, time, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Import config
try:
    from config import (
        SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
        EMAIL_FROM, SUPERVISOR_EMAIL
    )
    EMAIL_ENABLED = all([SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD,
                         EMAIL_FROM, SUPERVISOR_EMAIL])
except (ImportError, AttributeError):
    EMAIL_ENABLED = False

try:
    from config import OUTPUT_DIR, OVERVIEW_CSV, DAILY_SUMMARY_CSV
except (ImportError, AttributeError):
    OUTPUT_DIR = Path('output')
    OVERVIEW_CSV = OUTPUT_DIR / 'overview.csv'
    DAILY_SUMMARY_CSV = OUTPUT_DIR / 'daily_summary.csv'

STATE_FILE = Path(OUTPUT_DIR) / '.watchdog_state.json'
COLLECT_LOG = Path('collect-solar-data-crontab.log')

# Collection schedule: */15 4-23 in crontab
COLLECT_START = time(4, 0)
LAST_SLOT = time(23, 45)
STALE_LIMIT = timedelta(minutes=50)      # ~3 missed runs before alerting
SUMMARY_CHECK_AFTER_HOUR = 6             # summary cron runs at 5 AM
REMIND_BASE = timedelta(hours=24)        # reminders back off: 1d, 2d, 4d, ...
REMIND_MAX = timedelta(days=7)           # ... capped at weekly


def last_scheduled_run(now):
    """Timestamp of the most recent scheduled collection run at time `now`"""
    today_first = datetime.combine(now.date(), COLLECT_START)
    today_last = datetime.combine(now.date(), LAST_SLOT)
    if now >= today_last:
        return today_last
    if now >= today_first:
        return now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    return today_last - timedelta(days=1)


def read_last_timestamp(csv_path):
    """Timestamp of the last data row in overview.csv, or None"""
    try:
        with open(csv_path) as f:
            last = deque(f, maxlen=1)
    except OSError:
        return None
    if not last:
        return None
    field = last[0].split(',', 1)[0].strip()
    try:
        return datetime.strptime(field, '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return None


def find_problems(now, overview_csv=None, daily_csv=None):
    """Return {problem_key: description} for everything currently wrong"""
    overview_csv = Path(overview_csv or OVERVIEW_CSV)
    daily_csv = Path(daily_csv or DAILY_SUMMARY_CSV)
    problems = {}

    last_row = read_last_timestamp(overview_csv)
    if last_row is None:
        problems['overview-missing'] = f'{overview_csv} is missing or has no readable data rows'
    elif last_scheduled_run(now) - last_row > STALE_LIMIT:
        age = now - last_row
        hours = age.total_seconds() / 3600
        problems['collection-stalled'] = (
            f'No new data in {overview_csv} since {last_row} '
            f'({hours:.1f} hours ago) — collect-solar-data.py is not getting data from the PVS6'
        )

    if now.hour >= SUMMARY_CHECK_AFTER_HOUR:
        yesterday = (now.date() - timedelta(days=1)).isoformat()
        found = False
        try:
            with open(daily_csv) as f:
                found = any(row['Date'] == yesterday for row in csv.DictReader(f))
        except OSError:
            pass
        if not found:
            problems['summary-missing'] = (
                f'No {yesterday} row in {daily_csv} — daily-solar-summary.py did not run or had no data'
            )

    return problems


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def tail_of_log(n=12):
    try:
        with open(COLLECT_LOG) as f:
            return ''.join(deque(f, maxlen=n))
    except OSError:
        return '(no collector log found)'


def send_email(subject, html_body):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = EMAIL_FROM
    msg['To'] = SUPERVISOR_EMAIL
    msg.attach(MIMEText(html_body, 'html'))
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)


def alert_body(problems, now):
    items = ''.join(f'<li>{desc}</li>' for desc in problems.values())
    return f"""
    <html><body>
    <h2>⚠️ Solar monitoring problem detected</h2>
    <p>The cron health watchdog on the Raspberry Pi found at {now:%Y-%m-%d %H:%M}:</p>
    <ul>{items}</ul>
    <p>Last lines of the collector log:</p>
    <pre>{tail_of_log()}</pre>
    <p>If the collector log shows connection timeouts to 172.27.153.1, the PVS6
    has likely stopped responding on its LAN port and needs a power cycle
    (breaker off ~60 seconds).</p>
    </body></html>
    """


def main():
    now = datetime.now()

    if '--test' in sys.argv:
        if not EMAIL_ENABLED:
            print('❌ Email not configured in config.py, cannot send test email')
            return 1
        send_email('🔔 Solar watchdog test email',
                   f'<html><body><p>Test email from cron-health-watchdog.py '
                   f'on the Raspberry Pi at {now:%Y-%m-%d %H:%M:%S}. '
                   f'Alerting works.</p></body></html>')
        print(f'✓ Test email sent to {SUPERVISOR_EMAIL}')
        return 0

    if not EMAIL_ENABLED:
        print(f'{now:%Y-%m-%d %H:%M:%S} - Watchdog: ❌ email not configured, cannot alert')
        return 1

    problems = find_problems(now)
    state = load_state()
    prev_problems = set(state.get('problems', []))
    last_alert = None
    if state.get('last_alert'):
        last_alert = datetime.strptime(state['last_alert'], '%Y-%m-%d %H:%M:%S')

    if problems:
        is_new = bool(set(problems) - prev_problems)
        count = state.get('alert_count', 0)
        remind_after = min(REMIND_BASE * (2 ** max(count - 1, 0)), REMIND_MAX)
        reminder_due = last_alert is None or now - last_alert >= remind_after
        if is_new or reminder_due:
            prefix = 'ALERT' if is_new else f'still down (reminder #{count})'
            send_email(f'⚠️ Solar monitor {prefix}: {next(iter(problems.values()))[:80]}',
                       alert_body(problems, now))
            state['last_alert'] = now.strftime('%Y-%m-%d %H:%M:%S')
            state['alert_count'] = count + 1
            print(f'{now:%Y-%m-%d %H:%M:%S} - Watchdog: ❌ {len(problems)} problem(s), email sent')
        else:
            print(f'{now:%Y-%m-%d %H:%M:%S} - Watchdog: ❌ {len(problems)} problem(s), '
                  f'next reminder after {remind_after} from last alert')
        state['problems'] = sorted(problems)
        save_state(state)
    else:
        if prev_problems:
            send_email('✅ Solar monitor recovered',
                       f'<html><body><p>Data collection is flowing again as of '
                       f'{now:%Y-%m-%d %H:%M}. Previous problem(s): '
                       f'{", ".join(sorted(prev_problems))}.</p></body></html>')
            print(f'{now:%Y-%m-%d %H:%M:%S} - Watchdog: ✅ recovered, email sent')
        else:
            print(f'{now:%Y-%m-%d %H:%M:%S} - Watchdog: ✓ all checks passed')
        save_state({'problems': [], 'last_alert': None})
    return 0


if __name__ == '__main__':
    sys.exit(main())
