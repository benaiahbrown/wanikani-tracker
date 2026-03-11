# WaniKani Dashboard (Frontend)

`wanikani_dashboard.py` — A Flask web UI that visualizes WaniKani progress over time using snapshot history from the tracker.

## Usage

```bash
python3 wanikani_dashboard.py              # Start on port 8082
python3 wanikani_dashboard.py --port 9000   # Custom port
```

Then open `http://localhost:8082` in a browser.

## Architecture

Single-file Flask app with embedded HTML/JS/CSS. No build step, no external frontend tooling.

- **Backend**: One API endpoint (`/api/history`) that reads `data/wanikani_history.json` and returns it as JSON.
- **Frontend**: Inline HTML page using Chart.js 4, chartjs-adapter-date-fns (time axis), and chartjs-plugin-annotation (reference lines/ranges).

The dashboard is read-only — it never writes data. All data collection is done by `wanikani_tracker.py`.

## Views

The UI has two tabs: **Progress** and **Cohort Comparison**.

---

### Progress Tab

#### Summary Bar

Five stat cards showing the latest snapshot values:
- **Current Level** — `snapshot.level`
- **Kanji Learned** — `snapshot.kanji_learned` (Guru+ count)
- **Vocab Learned** — `snapshot.vocab_learned` (Guru+ count)
- **Overall Accuracy** — `snapshot.accuracy.overall_pct` (see tracker README for formula)
- **Days Studied** — `snapshot.days_studied` (days since your WaniKani start date)

#### Level-Up Panel

Shown when `snapshot.level_up.status === "in_progress"`. Displays:

- **Progress bar**: `already_guru / guru_needed * 100%` — How close to the 90% Guru threshold for leveling up.
- **Remaining count**: How many more kanji need to reach Guru, and how many aren't in lessons yet.
- **Optimistic estimate**: Time assuming perfect reviews (hours or days + target date). Calculated as `realistic_hours / accuracy_multiplier`.
- **Realistic estimate**: Time adjusted for your actual accuracy (hours or days + target date). The `accuracy_multiplier` value is shown (e.g., "1.23x adj").
- **Stage donut chart**: Doughnut chart breaking down current-level kanji by SRS stage (Initiate through Burned). Color-coded by stage.

When `status === "ready"`, shows a "Ready to level up!" message instead.

#### Chart 1: Level Progress

Line chart over time. Three datasets:
- **Level** (red, filled) — `snapshot.level` at each date
- **N2 Target** (yellow dashed) — Horizontal line at level 48
- **N1 Target** (green dashed) — Horizontal line at level 60

Y-axis: 0-65.

#### Chart 2: Items Learned (Guru+)

Line chart over time. Three datasets:
- **Learned (Guru+)** (cyan, filled) — `snapshot.kanji_learned`
- **In Progress** (purple, filled) — `snapshot.kanji_in_progress`
- **Vocab Learned** (orange, dashed) — `snapshot.vocab_learned`

#### Chart 3: Kanji SRS Distribution

Stacked bar chart over time. Five stacked series:
- **Apprentice** (purple) — `snapshot.srs.buckets.Apprentice`
- **Guru** (cyan) — `snapshot.srs.buckets.Guru`
- **Master** (blue) — `snapshot.srs.buckets.Master`
- **Enlightened** (yellow) — `snapshot.srs.buckets.Enlightened`
- **Burned** (gray) — `snapshot.srs.buckets.Burned`

Shows how items flow through the SRS pipeline over time.

#### Chart 4: Accuracy Trend

Line chart over time. Five datasets:
- **Meaning** (green, solid) — `snapshot.accuracy.meaning_pct` (kanji)
- **Reading** (orange, solid) — `snapshot.accuracy.reading_pct` (kanji)
- **Overall** (white, dashed) — `snapshot.accuracy.overall_pct` (kanji)
- **Vocab Meaning** (light green, dashed) — `snapshot.vocab_accuracy.meaning_pct`
- **Vocab Reading** (light orange, dashed) — `snapshot.vocab_accuracy.reading_pct`

Y-axis: 60%-100%.

#### Chart 5: JLPT Kanji Coverage %

Line chart over time. Five datasets (N5 through N1), each showing `snapshot.jlpt_coverage[level].pct` — the percentage of kanji in that JLPT level's WK range that are at Guru+.

Y-axis: 0%-100%.

#### Chart 6: N2 / N1 Prediction Timeline

Line chart showing how the **realistic predicted date** for N2 and N1 changes over time. As you collect more snapshots, you can see whether your estimated completion date is converging or drifting.

- X-axis: snapshot dates
- Y-axis: predicted completion date (time axis, month granularity)
- **N2 Est. Date** (yellow) — `snapshot.predictions.level_based.N2.realistic.date`
- **N1 Est. Date** (green) — `snapshot.predictions.level_based.N1.realistic.date`

---

### Cohort Comparison Tab

Compares your stats against hardcoded community benchmarks from WaniKani forums. There is no WaniKani API for community data, so these are static reference values.

#### Community Benchmarks (hardcoded)

```
Pace (days/level):
  Speed Runner: 7    Fast: 10    Median: 14    Steady: 20    Casual: 30

Accuracy (%):
  Meaning  — Top 10%: 97    Median: 92    Bottom 25%: 85
  Reading  — Top 10%: 90    Median: 82    Bottom 25%: 72
  Overall  — Top 10%: 93    Median: 87    Bottom 25%: 78

Sessions per day:
  High: 3.0    Median: 1.8    Low: 1.0

Streaks (days):
  Dedicated: 60    Good: 30    Average: 15    Casual: 7

Kanji per level: 33 (used for trajectory reference lines)
```

#### Chart 1: Pace — Days per Level

Horizontal bar chart. Your average days/level is shown as "You" alongside the 5 community tiers. Calculated from `snapshot.pace.avg`.

Color: white bar for you, colored bars for benchmarks.

#### Chart 2: Accuracy vs Community

Grouped bar chart with 3 categories (Meaning, Reading, Overall):
- **You** — Your accuracy values from `snapshot.accuracy`. Bar color is dynamic:
  - Green if >= community median
  - Yellow if >= bottom 25%
  - Red if below bottom 25%
- **Community Median** — Dashed gray bars

Background annotation boxes show the top-10% to bottom-25% range for each category.

#### Chart 3: Items Learned Trajectory

Line chart with days studied on x-axis, items on y-axis:
- **Your Kanji** (cyan, filled) — Plotted from all snapshots: `(days_studied, kanji_learned)`
- **Your Vocab** (purple, dashed) — `(days_studied, vocab_learned)`
- **Reference lines** (dashed) — Expected kanji count at different paces:
  - Fast (7d/level): `days / 7 * 33` kanji
  - Median (14d/level): `days / 14 * 33` kanji
  - Casual (25d/level): `days / 25 * 33` kanji

Where 33 = approximate kanji per WaniKani level.

#### Chart 4: Sessions per Day (Last 30 Days)

Bar chart showing daily session counts from `snapshot.sessions_streaks.daily_sessions`. Each bar is color-coded:
- Green if >= 3.0 (high)
- Cyan if >= 1.8 (median)
- Yellow if > 0
- Transparent if 0

Three horizontal annotation lines:
- **Community Median** (yellow dashed) at 1.8
- **High** (green dashed) at 3.0
- **Your Average** (white solid) — `snapshot.sessions_streaks.sessions_per_day_avg`

#### Chart 5: Study Streaks

Not a chart — stat cards + a gauge bar.

Four stat cards:
- **Current Streak** (red) — `sessions_streaks.current_streak` consecutive days
- **Longest Streak** (yellow) — `sessions_streaks.longest_streak` all-time max
- **Total Review Days** (cyan) — `sessions_streaks.total_review_days` distinct active days
- **Sessions/Day 7d avg** (purple) — `sessions_streaks.sessions_per_day_recent_7d`

**Gauge bar**: Maps current streak to a 0-100% bar where 60 days = 100% (the "Dedicated" benchmark). Gauge markers: 0, Casual (7d), Avg (15d), Good (30d), Dedicated (60d+).

`gauge_percent = min(current_streak / 60 * 100, 100)`

---

## How Sessions and Streaks Are Calculated

See the tracker README for the full algorithm. In brief:

- **Sessions**: Activity timestamps clustered by 30-minute gaps within each UTC day. Sources: review_statistics timestamps + assignment start/pass timestamps.
- **Current Streak**: Consecutive calendar days with activity, counting back from today.
- **Longest Streak**: Longest run of consecutive active days in the full history.

## Dependencies

- `flask` — Web server
- `python-dotenv` — `.env` loading (for consistency, though the dashboard itself doesn't use API keys)
