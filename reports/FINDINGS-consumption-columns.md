# Why "Daily Site Consumption" Doesn't Match Your Utility Bill

**Investigation date:** 2026-08-01
**Data examined:** `output/overview.csv` (21,711 samples, 2025-10-17 15:42 through 2026-08-01 07:45), `output/daily_summary.csv` (273 rows, 2025-10-17 through 2026-07-31), and all 21,711 raw JSON snapshots in `output/raw_JSON_output_files/`

**Code examined:** `collect-solar-data.py`, `daily-solar-summary.py`, `README.md`, the installed crontab, and `github-SunStrong-Management-pypvs-varserver-variables-public-pvs6.csv`

**Short version:** The column labeled `Daily Net Grid (kWh)` is actually your home's total electricity consumption. The column labeled `Daily Site Consumption (kWh)` is your consumption *plus* your solar production added together — a double-count. The labels are, in effect, wrong. Your real net grid figure isn't in the spreadsheet at all, but it can be calculated from data you already have.

---

## Part 0: Vocabulary

Everything defined here is used later in the report. If a term is unfamiliar, it's defined here and nowhere else.

### Units

| Term | Plain English |
|---|---|
| **kW** (kilowatt) | A rate of energy flow — how fast electricity is moving *right now*. Like the speedometer in a car. A microwave draws about 1 kW while it's running. |
| **kWh** (kilowatt-hour) | An amount of energy — a rate multiplied by time. Like the odometer in a car. Running a 1 kW microwave for one hour uses 1 kWh. Your utility bills you in kWh. |
| **Instantaneous value** | A kW reading — a snapshot of the flow rate at the moment it was sampled. |
| **Lifetime counter** (also **cumulative counter**, or **register**) | A kWh number that only ever counts up, from the day the equipment was installed. To find out how much energy moved during a period, you read the counter at the start, read it at the end, and subtract. The difference is called a **delta**. |

### Hardware

| Term | Plain English |
|---|---|
| **PV** | **Photovoltaic** — the technical word for solar panels. "PV production" = electricity your panels made. |
| **Inverter** | A small box attached to each solar panel. Panels produce DC (direct current) power; the inverter converts it to AC (alternating current), which is what your house and the grid use. Your system has 25 of them, so 25 panels. |
| **PVS6** | **PV Supervisor, model 6** — the SunPower monitoring gateway installed at your house. It's a small computer that talks to all 25 inverters and to the energy meters, adds everything up, and serves the results over your network. This repo's scripts read from it. |
| **CT** (**current transformer**), sometimes called a **CT clamp** | A donut-shaped sensor that clamps around an electrical wire and measures how much current is flowing through it, without having to cut into the wire. The PVS6 uses CTs to measure energy flows. **Where a CT is physically clamped determines what it is measuring** — this turns out to be the entire crux of this report. |
| **Meter** (in PVS6 terminology) | A pair of CTs plus the electronics that read them. Your PVS6 has two: a **production meter** and a **consumption meter**. |
| **Load** | Anything that consumes electricity — lights, fridge, air conditioner. "Site load" = the total electrical demand of your house. |
| **Service entrance** / **main panel** | Where the utility's wires enter your house and connect to your breaker box. |
| **Grid tie-point** | The exact spot where your house's wiring meets the utility's wiring. Energy crossing this point in one direction is *import* (you buy it); crossing the other direction is *export* (you sell it back). |

### Concepts

| Term | Plain English |
|---|---|
| **Import** | Energy flowing from the utility into your house. You pay for this. |
| **Export** | Energy flowing from your house out to the utility, because your panels are making more than you're using at that moment. You get credit for this. |
| **Net grid** | Import minus export. A single signed number: positive means you took more than you gave, negative means you gave more than you took. "Net" here just means "after cancelling the two directions against each other." |
| **Bidirectional flow** | Energy that can move either direction through the same wire at different times. The wire at your grid tie-point is bidirectional: import at night, export at midday. |
| **Net metering** / **NEM** (**Net Energy Metering**) | The billing arrangement where your utility credits you for exported solar. The relevant consequence for us: on a net-metered home, energy at the grid tie-point genuinely flows *both* directions during a normal day. |
| **Gross consumption** vs. **net consumption** | Two different things a consumption meter can measure. **Gross consumption** = everything your house uses, no matter where it came from (solar or grid). **Net consumption** = only the part that came from the grid. On a sunny day these are very different numbers. |
| **Cron** | The Unix scheduler that runs a program automatically on a timetable. This repo uses cron to run `collect-solar-data.py` every 15 minutes and `daily-solar-summary.py` once a day. |
| **CSV** | **Comma-Separated Values** — a plain-text spreadsheet file. One line per row, columns separated by commas. |
| **JSON** | **JavaScript Object Notation** — a plain-text data format. The PVS6 replies in JSON; the collector saves each reply as a file so there's a permanent raw record. |
| **VarServer** | The name of the PVS6's data interface — "variable server." You ask it for variables by name and it returns their current values. The names look like file paths: `/sys/livedata/pv_en`. |

---

## Part 1: What the code actually does

The pipeline has two stages.

### Stage 1 — `collect-solar-data.py`, every 15 minutes

It asks the PVS6 for every variable it knows about (`collect-solar-data.py:52`), then picks out six of them (`collect-solar-data.py:87-92`) and appends one row to `output/overview.csv`.

Three of those six are lifetime kWh counters, and they become the three columns at issue:

| Column in `overview.csv` | PVS6 variable it comes from | Official name in the PVS6 variable dictionary |
|---|---|---|
| `Lifetime PV Production (kWh)` | `/sys/livedata/pv_en` | "Production Energy (kWh)" |
| `Lifetime Site Consumption (kWh)` | `/sys/livedata/site_load_en` | "Site Load Energy (kWh)" |
| `Lifetime Net Grid (kWh)` | `/sys/livedata/net_en` | "Net Consumption Energy (kWh)" |

(The official names are from `github-SunStrong-Management-pypvs-varserver-variables-public-pvs6.csv`, the variable dictionary included in this repo. The suffix `_en` means *energy*, i.e. a kWh counter; `_p` means *power*, i.e. a kW instantaneous reading.)

The other three are the matching instantaneous kW readings: `pv_p`, `site_load_p`, `net_p`.

**Important:** this script does no arithmetic. It copies the PVS6's numbers verbatim. Whatever is wrong is either upstream in the PVS6 or in how the columns are named — not in this file's math.

### Stage 2 — `daily-solar-summary.py`, once a day

It computes each day's totals by subtracting lifetime counters (`daily-solar-summary.py:149-165`):

```python
daily_pv          = last['Lifetime PV Production (kWh)']    - first['Lifetime PV Production (kWh)']
daily_consumption = last['Lifetime Site Consumption (kWh)'] - first['Lifetime Site Consumption (kWh)']
daily_net         = last['Lifetime Net Grid (kWh)']         - first['Lifetime Net Grid (kWh)']
```

Those three deltas become `Daily PV Production`, `Daily Site Consumption`, and `Daily Net Grid` in `output/daily_summary.csv` and in the Google Sheet.

Again: correct subtraction of whatever numbers it was given. The problem is in the numbers.

---

## Part 2: The first clue — one column is not a measurement

Take the very first row of `output/overview.csv`:

```
Lifetime PV Production:    37,453.87 kWh
Lifetime Site Consumption: 71,073.89 kWh
Lifetime Net Grid:         33,620.02 kWh
```

Notice: 37,453.87 + 33,620.02 = 71,073.89. Production plus net grid equals site consumption, exactly.

That is not a coincidence. Checking all 21,711 rows:

- The identity **`site_load_en = pv_en + net_en`** holds in **21,684 of 21,711** samples. (The 27 exceptions are all sub-0.002 kWh rounding noise or the one meter glitch discussed in Part 6.)
- The same identity holds for the instantaneous kW values: **`site_load_p = pv_p + net_p`** in 21,684 of 21,711 samples.

**Conclusion: `site_load_en` is not measured by any sensor.** There is no third CT anywhere in the house measuring total household demand. The PVS6 is *computing* site load by adding two other numbers together.

That is a completely standard and normally correct thing for a PVS6 to do — but only under one specific assumption, which is the subject of the next section.

---

## Part 3: The assumption behind that formula, and why it's false here

### The assumption

`site load = production + net grid` is the correct formula **if and only if** the consumption CTs are clamped at the **grid tie-point**, measuring bidirectional net flow.

Here's the reasoning, in plain terms. Every kWh your house uses comes from exactly one of two places: your panels, or the grid. So:

```
what the house used  =  what the panels made  +  what came in from the grid
```

with the crucial detail that "what came in from the grid" must be a **signed** number. When you're exporting, it must go *negative*, so that the formula subtracts the exported energy back out — that energy was made by the panels but never used by the house.

A worked example. Sunny midday: panels make 6 kW, house is using 1 kW, so 5 kW flows out to the grid.

- Net grid = **−5 kW** (negative: exporting)
- Formula: 6 + (−5) = **1 kW**. Correct — that's what the house is using.

Now suppose the CTs never report negative, and instead the meter reports +0.2 kW:

- Formula: 6 + 0.2 = **6.2 kW**. Wrong, and inflated by almost the entire solar output.

### Why we know the CTs here are not seeing bidirectional flow

Three independent pieces of evidence, each sufficient on its own.

**Evidence A — the reverse-flow counter has never once moved.**

Each PVS6 meter keeps three separate lifetime registers:

| Register | Meaning |
|---|---|
| `posLtea3phsumKwh` | Lifetime energy that flowed in the **positive** direction. ("pos" = positive, "Ltea" = lifetime energy accumulated, "3phsum" = summed across all three electrical phases.) |
| `negLtea3phsumKwh` | Lifetime energy that flowed in the **negative** (reverse) direction. |
| `netLtea3phsumKwh` | Positive minus negative — the net. |

On the consumption meter (its serial ends in `c`, which is what marks it as the *consumption* meter; the production one ends in `p`), across **every one of the 21,711 raw JSON snapshots**:

```
negLtea3phsumKwh = 0.000000     (in all 43,420 meter records, both meters, every file)
posLtea3phsumKwh = netLtea3phsumKwh     (positive and net are identical)
```

Verified with a scan of every raw file:

```
$ grep -h '"/sys/devices/meter/[01]/negLtea3phsumKwh"' output/raw_JSON_output_files/*.json \
    | sed 's/.*: //' | sort | uniq -c
  43420 "0.000000",
```

A CT at the grid tie-point of a solar home would have accumulated thousands of kWh in the negative register over nine months. Yours has accumulated exactly zero. **This sensor has never in its life seen energy flow backwards.**

**Evidence B — instantaneous net power is never negative.**

Across all 21,711 rows of `overview.csv`, `Current Net Power (kW)` is negative **0 times**. Nine months of a 25-panel system, and never one moment of export. Not plausible if the sensor were positioned to see export.

**Evidence C — the shape of the data over a day. This is the decisive one.**

Here are two days side by side: one overcast (peak production 2.4 kW) and one clear (peak production 6.7 kW). Watch the middle column, `net_p`, the reading from the consumption CTs.

```
       2026-05-06  (overcast)                    2026-05-11  (clear)
       pv_p    net_p   site_load_p               pv_p    net_p   site_load_p
04:00  0.01    0.26    0.27                      0.02    0.27    0.29
06:00  0.00    0.25    0.25                      0.06    0.26    0.32
08:00  0.63    0.23    0.86                      1.27    0.23    1.50
10:00  0.78    0.21    0.99                      2.44    0.22    2.66
12:00  1.77    0.28    2.05                      5.19    0.27    5.46
14:00  2.38    0.21    2.59                      6.65    0.27    6.92
16:00  1.38    0.25    1.63                      6.49    0.27    6.76
18:00  0.94    0.25    1.19                      4.96    0.23    5.19
20:00  0.02    0.27    0.29                      0.45    0.23    0.68
22:00  0.01    0.26    0.26                      0.01    0.22    0.23
```

`net_p` sits at a nearly constant ~0.25 kW — at 4 a.m., at solar noon, on a cloudy day, on a sunny day. It is completely indifferent to the sun. Meanwhile `site_load_p` (the rightmost column) is visibly just the solar curve with 0.25 added to it.

Now consider what that would mean if `net_p` really were grid import. Your house would have to be consuming *exactly* production + 0.25 kW at every single moment — ramping from 0.25 kW at dawn up to 6.9 kW at 2 p.m. and back down, tracking the clouds in real time, on both of these days and on every other day for nine months. Nothing in a house behaves that way. And there's no battery that could be smoothing it: `/sys/livedata/ess_p` and `/sys/livedata/soc` (**ESS** = **Energy Storage System**, i.e. a home battery; **SOC** = **state of charge**, how full it is) both read `nan` — "not a number," the value returned when no such equipment exists.

**Corroboration in the daily totals.** The same thing shows up at day scale. Ten consecutive days in May, straight from `daily_summary.csv`:

```
Date          Daily PV    Daily Site Consumption    Daily Net Grid
2026-05-05      30.63              37.31                 6.68
2026-05-06      15.99              23.58                 7.59
2026-05-07      40.99              47.96                 6.97
2026-05-08      40.91              48.53                 7.62
2026-05-09      37.64              44.41                 6.77
2026-05-10      28.65              36.62                 7.97
2026-05-11      54.83              62.08                 7.25
2026-05-12      35.58              42.49                 6.91
2026-05-13      17.92              25.19                 7.27
2026-05-14      29.84              37.48                 7.64
```

Production swings by a factor of 3.4 (15.99 to 54.83 kWh) while "Net Grid" stays pinned between 6.68 and 7.97 kWh. If that column were grid import, then on 2026-05-06 the house supposedly needed 23.58 kWh while the panels delivered only 15.99 — the missing ~7.6 kWh had to come from the grid, and indeed it says 7.59. But on 2026-05-11 the house supposedly needed 62.08 kWh while the panels delivered 54.83 — and the shortfall is again ~7.25. The "shortfall" is suspiciously constant because it isn't a shortfall at all: it's a directly measured quantity, and the "consumption" column is the derived one.

Read the other way, the data is immediately sensible: the house used about 7 kWh per day for ten days (a steady ~0.3 kW baseline — nobody home, just the fridge and standby loads), while the panels made anywhere from 16 to 55 kWh depending on the weather, and the surplus was exported.

### The diagnosis

Your consumption CTs are clamped on the **load side** — downstream of where the solar ties in, so they only ever see energy flowing *toward* the house. That's why they never go negative. They are measuring **gross consumption**: your true, total household usage.

But your PVS6 is configured for the other arrangement — it believes those CTs are at the grid tie-point measuring **net consumption**, so it applies `site load = production + net`. Feeding a gross-consumption reading into a formula that expects a net-consumption reading **adds your solar production to your consumption instead of reconciling the two.**

This is a PVS6 wiring/configuration mismatch, not a coding error in this repo. `collect-solar-data.py` faithfully reports what the PVS6 says. But the repo's column *names* inherit the PVS6's mistaken interpretation and pass it to your spreadsheet.

---

## Part 4: What your columns actually mean

| Spreadsheet column | What the name implies | What it actually is |
|---|---|---|
| `Daily PV Production (kWh)` | Solar generated | ✅ Correct — solar generated |
| `Daily Net Grid (kWh)` | Import minus export | ❌ Actually your **total household consumption** — gross, from all sources |
| `Daily Site Consumption (kWh)` | Total household consumption | ❌ Actually **consumption + production added together** — meaningless as a physical quantity |
| *(not present)* | — | Your genuine net grid figure is missing from the sheet entirely |

This is exactly the mismatch you noticed. `Daily Net Grid` lines up with your utility's usage figure because it *is* your household usage. And `Daily Site Consumption` is too high by the full amount of your solar production — roughly double in winter, and worse in summer when production is high.

### Recovering the real numbers

No new sensors or reconfiguration needed; the information is already in the data.

```
true home consumption  =  Daily Net Grid          (the existing column, just renamed)

true net grid          =  Daily Net Grid  −  Daily PV Production
                          (negative = net export, positive = net import)
```

Applied to your history. Two rows are excluded as unusable: the corrupted 2026-04-23 row (see 6a) and the 16-day "catch-up" lump dated 2026-07-31 (see 6c). July therefore covers only 07-01 through 07-15.

```
month     days   production   consumption   net grid (+ = import, − = export)   PVS "site consumption"
2025-10     15          161           445                      +284                         606
2025-11     30          214           862                      +648                       1,075
2025-12     31          153           886                      +733                       1,039
2026-01     31          242         1,015                      +773                       1,257
2026-02     28          386           932                      +545                       1,318
2026-03     31          572         1,021                      +450                       1,593
2026-04     28          869           791                       −78                       1,660
2026-05     31        1,229           520                      −708                       1,749
2026-06     30        1,386           636                      −749                       2,022
2026-07     15          746           359                      −388                       1,105
─────────────────────────────────────────────────────────────────────────────────────────────────
 total     270        5,957         7,468                    +1,511                      13,425
```

That is the classic solar-home profile: importing through the dark winter months, flipping to net export in April, exporting heavily through summer.

The rightmost column is what your spreadsheet reports today. Over these 270 days it totals 13,425 kWh against a true consumption of 7,468 kWh — **inflated by a factor of 1.8**, the inflation being exactly the 5,957 kWh your panels produced.

One caveat when comparing the net-grid column to a bill: this is a *monthly* net. Utilities net imports and exports over much shorter intervals (typically 15 minutes or an hour) and often price them differently by time of day under **TOU** (**Time-Of-Use**) rates. So expect the sign and rough magnitude to agree with your bill, not the exact dollar figure.

---

## Part 5: How to verify this independently

Two checks you can do yourself.

**Check the utility meter during peak sun.** On a clear day around 1–2 p.m., look at the display on the utility meter at your service entrance. Most digital meters show either a direction arrow or a "delivered / received" indicator. If it shows energy being *received* (flowing out of your house), you are exporting — which the PVS6 currently claims never happens, and which confirms that `net_en` is not measuring the grid tie-point.

**Compare against total production.** Over 2026-05-01 through 2026-07-15 your panels produced 3,361 kWh, and the corrected consumption figure is 1,515 kWh. If the current `Daily Site Consumption` column were right, you'd have consumed 4,876 kWh in that window while importing 1,515 kWh — meaning you used every single kWh your panels produced, at the instant it was produced, for two and a half months, and never exported a watt. Your utility statement will show export credits if that's false.

---

## Part 6: Other problems found along the way

Three genuine defects in this repo's code (6a–6c), plus one hazard to be aware of if you change the code (6d). All are separate from the main issue in Parts 1–4.

### 6a. Lifetime counters are subtracted with no sanity check — one day reads −39,386 kWh

`daily-solar-summary.py:149-165` subtracts yesterday's counter from today's with no validation. Lifetime counters are supposed to only count up, but hardware occasionally glitches and resets to zero.

That happened on 2026-04-24. The consumption meter reported `0.00` from 04:00 to 06:00, then resumed at its correct value:

```
2026-04-23 23:45:03   Lifetime Net Grid = 39,424.82
2026-04-24 04:00:03   Lifetime Net Grid =      0.00     ← glitch
2026-04-24 06:15:03   Lifetime Net Grid = 39,427.06     ← recovered
```

Because the daily calculation happens to sample at 04:00, it picked up the zero. `output/daily_summary.csv:190` now reads:

```
2026-04-23, PV 23.63, Site Consumption 63.36, Net Grid −39,385.91, Lifetime Net Grid 0.0
2026-04-24, PV 51.04, Site Consumption 85.63, Net Grid  39,460.23
```

A single day recording negative thirty-nine thousand kWh. That row was written to the Google Sheet, and the monthly and yearly rollups (`daily-solar-summary.py:389-390` and `:843-844`) sum the daily values without filtering, so **every April, 2026, and all-time total in the reports is wrong.**

*Fix:* reject a delta that is negative or implausibly large, and write a blank rather than a nonsense number.

### 6b. Each "day" runs 04:00 to 04:00, not midnight to midnight

Counting samples by hour across all 21,711 rows:

```
hour:  04  05  06  07 ... 22  23    00  01  02  03
count: 1084 1083 1082 1086 ... 1088 1088     0   0   0   0
```

There are **no samples at all between midnight and 04:00**. The reason is right there in the crontab — the hour field reads `4-23`:

```
*/15 4-23 * * *  ... collect-solar-data.py
0 5 * * *        ... daily-solar-summary.py
```

("`*/15 4-23`" means: every 15 minutes, but only during hours 04 through 23.) So when `read_overview_for_date()` (`daily-solar-summary.py:101-119`) asks for the "first entry of the target date," it gets roughly 04:00, not 00:00.

The window is still a full 24 hours (04:00 today to 04:00 tomorrow), so the totals aren't wrong in magnitude — but each row labeled with a calendar date actually covers 04:00 on that date through 04:00 the next. Harmless for month-to-month comparison; a consistent four-hour offset if you're matching a specific day against a utility interval report.

*Fix:* either extend the collection schedule to run around the clock, or document the offset.

### 6c. The missing-data fallback silently produces a short day, and the outage gap is papered over by a hand-written lump row

Two related problems around the 2026-07-16 → 07-31 collection outage.

**The short-day fallback.** `daily-solar-summary.py:632-638`: when there's no data yet for the next day, it falls back to the last entry of the target date. That yields a roughly 20-hour "day" (04:00 to 23:45) instead of a full 24 hours, and nothing in the output CSV marks the row as partial — the warning goes only to the console log. `2026-07-15` is such a row.

**The catch-up row.** The last row of `daily_summary.csv` is:

```
2026-07-31, PV 736.22, Site Consumption 1209.97, Net Grid 473.75, Inverters Reporting 0,
  "ℹ️ Catch-up row: totals for 2026-07-16 → 2026-08-01 07:42 (PVS6 outage, no per-day data)"
```

This row is honestly labeled, and the labeling is good practice — but two things about it need flagging:

1. **No code in this repo produces it.** `grep -n "Catch-up" *.py` finds nothing. It was written into the CSV by hand or by some process outside this repo. (For the record: the file's modification time is 2026-08-01 07:54, during this investigation; it was not present when I first read the file a few minutes earlier.) So this is not behavior you can rely on happening again after the next outage.
2. **It is stamped with a single date but contains 16 days of energy.** Anything that groups by date — the monthly and yearly rollups at `daily-solar-summary.py:389-390` and `:843-844`, and any chart in the Google Sheet — will attribute 736 kWh of production to one calendar day. It also carries `Inverters Reporting = 0`, which is correct (there was no per-inverter data) but is the same value the code uses to mean "total failure."

*Fix:* record the actual time span each row covers in its own column (e.g. `Hours Covered`), so partial days, full days, and multi-day catch-up lumps are distinguishable by the code rather than only by a human reading the alert text. Then have the rollups either skip or pro-rate rows that don't cover ~24 hours.

### 6d. (Caution, not a current bug) Meter array indices are not stable

If you ever change the code to read the meters directly instead of going through `/sys/livedata/`, be aware that the PVS6's meter *numbering* can swap. Normally `/sys/devices/meter/0` is the production meter and `meter/1` is the consumption meter — but on 2026-02-12 and 2026-05-10 they traded places:

```
2026-02-12 06:30 —
  /sys/devices/meter/0/sn = PVS6M<serial>c     ← consumption meter, now at index 0
  /sys/devices/meter/1/sn = PVS6M<serial>p     ← production meter, now at index 1
```

Code that assumes "index 0 is production" would have silently swapped your production and consumption figures on those days. Key on the serial number suffix (`...p` vs `...c`) or on `prodMdlNm` (`PVS6M0400p` vs `PVS6M0400c`) instead.

The current code is unaffected, because `/sys/livedata/` is computed by the PVS6 itself and it resolves meters by serial number, not index. Confirmed on both swap dates: `pv_en` correctly tracked the `...p` meter and `net_en` the `...c` meter regardless of index.

---

## Part 7: Recommended fixes

**Highest value, no code change:** reinterpret the existing columns per Part 4 — treat `Daily Net Grid` as your household consumption, and compute true net grid as `Daily Net Grid − Daily PV Production`.

**In the code:**

1. Rename the columns so they say what they mean. Suggested: `Daily Site Consumption (kWh)` → `Daily Home Consumption (kWh)`, sourced from the `net_en` delta; add a new `Daily Net Grid (kWh)` computed as consumption minus production; drop the PVS6's `site_load_en` entirely, or keep it under a name like `PVS Site Load (unreliable — double-counts PV)`.
2. Add the reset/spike guard from 6a.
3. Update the column documentation at `README.md:43-68`, which currently repeats the incorrect meanings.
4. Optionally, read the two meters' `netLtea3phsumKwh` registers directly instead of the derived `livedata` values — keying on serial suffix per 6d. This bypasses the PVS6's faulty derivation at the source.

**On the hardware side (optional):** if you want the PVS6's own app and portal to show correct figures too, the underlying fix is at the PVS6 — either move the consumption CTs to the grid tie-point, or reconfigure the PVS6 to expect load-side (gross consumption) CTs. That's a SunPower/SunStrong installer task, not something this repo can fix. Note that changing it *would* change the meaning of `net_en` going forward, which would break the corrected math above — so if you do it, note the date.

**A note on existing history:** renaming columns in the code does not rewrite the rows already in your Google Sheet. Either rewrite the sheet from `daily_summary.csv` after fixing, or start a new tab so old and new rows aren't mixed under different definitions.
