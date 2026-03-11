# WaniKani Tracker (Backend)

`wanikani_tracker.py` — Fetches live data from the WaniKani API v2, computes analytics across seven dimensions, saves a daily snapshot, and renders a rich terminal report.

## Usage

```bash
python3 wanikani_tracker.py              # Full terminal report + save snapshot
python3 wanikani_tracker.py --refresh    # Force-refresh the kanji subjects cache
python3 wanikani_tracker.py --json       # Output raw JSON instead of the report
```

Requires `WANIKANI_API_KEY` in `.env`.

## Data Flow

1. **Fetch** — Pulls 7 endpoints from WaniKani API v2 (user, summary, kanji assignments, kanji review stats, vocab assignments, vocab review stats, level progressions, kanji subjects).
2. **Analyze** — Runs 7 compute functions over the raw data.
3. **Snapshot** — Saves a daily snapshot to `data/wanikani_history.json` (append-only, deduplicated by date). This file is what the dashboard reads.
4. **Render** — Prints a Rich terminal report (or JSON with `--json`).

### Caching

- **Subjects cache**: `data/wanikani_subjects_cache.json` — Kanji subject metadata (level, characters). Refreshed when older than 7 days or when `--refresh` is passed. Avoids re-fetching ~2000+ subjects on every run.
- **History**: `data/wanikani_history.json` — One snapshot per day. If run multiple times in a day, the existing entry for that date is replaced.

## How Every Metric Is Calculated

### 1. SRS Distribution (`compute_srs_distribution`)

Counts kanji (or vocab) assignments by WaniKani SRS stage:

| Bucket       | SRS Stages |
|-------------|-----------|
| Initiate    | 0         |
| Apprentice  | 1-4       |
| Guru        | 5-6       |
| Master      | 7         |
| Enlightened | 8         |
| Burned      | 9         |

- **Learned** = Guru + Master + Enlightened + Burned (stage >= 5)
- **In Progress** = Apprentice count (stages 1-4)

Applied separately for kanji and vocabulary assignments.

### 2. Accuracy (`compute_accuracy`)

Aggregates all `review_statistics` records:

- **Meaning Accuracy** = `meaning_correct / (meaning_correct + meaning_incorrect) * 100`
- **Reading Accuracy** = `reading_correct / (reading_correct + reading_incorrect) * 100`
- **Overall Accuracy** = `(meaning_correct + reading_correct) / (meaning_correct + meaning_incorrect + reading_correct + reading_incorrect) * 100`

Computed independently for kanji and vocabulary review statistics.

### 3. Pace (`compute_pace`)

Uses the `level_progressions` endpoint. For each completed level:

- **Days per level** = `(passed_at - started_at)` in fractional days

Aggregated stats:
- **Average** = Mean of all completed level durations
- **Recent Average** = Mean of the last 5 completed levels
- **Fastest / Slowest** = Min / max duration with level number
- **Std Dev** = Standard deviation of all level durations (requires >= 2 completed levels)

### 4. JLPT Coverage (`compute_jlpt_coverage`)

Maps each kanji to a JLPT level via its WaniKani level:

| JLPT | WK Levels |
|------|----------|
| N5   | 1-10     |
| N4   | 11-16    |
| N3   | 17-35    |
| N2   | 36-48    |
| N1   | 49-60    |

For each JLPT level:
- **Total** = Number of kanji subjects in that WK level range
- **Learned** = Assignments at SRS stage >= 5 (Guru+) for kanji in that range
- **In Progress** = Assignments at SRS stages 1-4 for kanji in that range
- **Coverage %** = `learned / total * 100`

### 5. Level-Up Estimate (`compute_level_up_estimate`)

Predicts time to reach the next WaniKani level. WaniKani requires **90% of a level's kanji at Guru+ (stage 5+)** to level up.

**SRS interval assumptions** (minimum hours per stage, assuming correct answers):

| Transition                | Hours |
|--------------------------|-------|
| Apprentice I -> II       | 4     |
| Apprentice II -> III     | 8     |
| Apprentice III -> IV     | 23    |
| Apprentice IV -> Guru I  | 47    |

**Accuracy multiplier**:
- `advance_probability = (reading_accuracy/100) * (meaning_accuracy/100)` — Both meaning AND reading must be correct in a single review to advance.
- `accuracy_multiplier = 1 / advance_probability` — Models how incorrect answers add extra review cycles.

**Per-item estimate**:
- For each non-Guru kanji at the current level, sum the remaining SRS intervals from its current stage to stage 5.
- Stage 0 (not started): uses the full path (4 + 8 + 23 + 47 = 82 hours).
- If the item has a future `available_at` timestamp, the wait time until that review replaces the current-stage interval; remaining stages are added after.
- Locked items (not yet assigned) use the full 82-hour path.

**Level-up timing**:
- All items are sorted by estimated hours-to-Guru.
- Level-up happens when the Nth fastest item reaches Guru, where N = `ceil(total_kanji * 0.9) - already_guru`.
- **Optimistic** = Nth item's time / accuracy_multiplier (assumes perfect reviews)
- **Realistic** = Nth item's time as-is (adjusted for your accuracy)

### 6. Predictions (`compute_predictions`)

Two independent approaches to predict N2 (level 48) and N1 (level 60) completion:

**Approach A — Level-based**:
- `remaining_levels = target_level - current_level`
- **Realistic** = `remaining_levels * recent_avg_pace` (last 5 levels)
- **Optimistic** = `remaining_levels * max(avg_pace - std_dev, fastest_level_pace)`
- **Pessimistic** = `remaining_levels * min(avg_pace + std_dev, slowest_level_pace)`

**Approach B — Coverage-based**:
- `kanji_per_day = total_kanji_learned / days_studied`
- For N2: needs all kanji in N5+N4+N3+N2 WK ranges. For N1: all kanji.
- `remaining = needed - learned`
- `est_days = remaining / kanji_per_day`

### 7. Sessions & Streaks (`compute_sessions_and_streaks`)

Since the `/reviews` endpoint returns 0 records with the current API token, activity is reconstructed from available timestamps:

**Timestamp sources**:
- `review_statistics[].data_updated_at` — Each item's last review time
- `review_statistics[].data.created_at` — When the review stat record was created
- `assignments[].data.started_at` — When a lesson was started
- `assignments[].data.passed_at` — When an assignment passed a level gate

**Sessions**:
- Timestamps are grouped by UTC date.
- Within each day, timestamps are sorted. A new "session" starts when the gap between consecutive timestamps exceeds **30 minutes**.
- **Sessions/day avg** = total sessions across all active days / number of active days
- **Sessions/day (7d)** = average sessions per day over the last 7 days (only counting days with activity)

**Streaks**:
- **Current streak** = Consecutive calendar days with activity, counting backwards from today. Breaks the moment a day has no activity.
- **Longest streak** = Maximum run of consecutive calendar days with activity across the entire history.
- **Total review days** = Count of distinct calendar days that had any activity.

### Days Studied

`days_studied = today - start_date`. The start date is resolved in this order:
1. `WANIKANI_START_DATE` environment variable (YYYY-MM-DD format) if set in `.env`
2. Otherwise, the `started_at` field from the WaniKani `/user` API response (your account creation date)

## Snapshot Schema

Each snapshot saved to `wanikani_history.json`:

```
date              — ISO date string (YYYY-MM-DD)
level             — Current WaniKani level (integer)
days_studied      — Days since start date (env var or WK account start)
kanji_learned     — Kanji at Guru+ (integer)
kanji_in_progress — Kanji at Apprentice (integer)
srs               — { buckets: {Initiate, Apprentice, Guru, Master, Enlightened, Burned}, total, learned, in_progress }
accuracy          — { meaning_pct, reading_pct, overall_pct, total_reviews }
vocab_learned     — Vocab at Guru+ (integer)
vocab_in_progress — Vocab at Apprentice (integer)
vocab_srs         — Same structure as srs, for vocabulary
vocab_accuracy    — Same structure as accuracy, for vocabulary
pace              — { completed: [{level, days}], avg, recent_avg, fastest, slowest, std_dev }
jlpt_coverage     — { N5..N1: { total, learned, in_progress, pct } }
level_up          — { status, total_kanji, guru_needed, already_guru, still_needed, stage_counts, optimistic_hours, realistic_hours, optimistic_date, realistic_date }
predictions       — { level_based: {N2, N1: {optimistic, realistic, pessimistic}}, coverage_based: {N2, N1: {learned, needed, remaining, kanji_per_day, est_days, est_date}} }
sessions_streaks  — { sessions_per_day_avg, sessions_per_day_recent_7d, daily_sessions: {date: count}, current_streak, longest_streak, total_review_days }
```

## Dependencies

- `requests` — WaniKani API calls
- `rich` — Terminal report formatting
- `python-dotenv` — `.env` file loading
- `statistics` (stdlib) — Mean, stdev for pace calculations
