"""
WaniKani Progress Tracker — predicts N2 and N1 kanji proficiency dates.

Fetches live data from WaniKani API v2, analyzes pace, accuracy, and SRS
distribution, then renders a rich terminal report with JLPT predictions.

Usage:
  python3 wanikani_tracker.py              # Full report
  python3 wanikani_tracker.py --refresh    # Refresh subjects cache
  python3 wanikani_tracker.py --json       # Raw JSON output
"""

import argparse
import datetime
import json
import os
import statistics
import sys
from collections import defaultdict

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

BASE_URL = "https://api.wanikani.com/v2"
API_KEY = os.environ.get("WANIKANI_API_KEY", "")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
SUBJECTS_CACHE_PATH = os.path.join(DATA_DIR, "wanikani_subjects_cache.json")
HISTORY_PATH = os.path.join(DATA_DIR, "wanikani_history.json")
CACHE_MAX_AGE_DAYS = 7

def _parse_start_date() -> datetime.date:
    """Read WANIKANI_START_DATE from env (YYYY-MM-DD), or derive from API later."""
    val = os.environ.get("WANIKANI_START_DATE", "")
    if val:
        return datetime.date.fromisoformat(val)
    return None

# WaniKani level thresholds for approximate JLPT coverage
JLPT_LEVEL_RANGES = {
    "N5": (1, 10),
    "N4": (11, 16),
    "N3": (17, 35),
    "N2": (36, 48),
    "N1": (49, 60),
}
JLPT_LEVEL_TARGETS = {"N5": 10, "N4": 16, "N3": 35, "N2": 48, "N1": 60}

SRS_STAGE_NAMES = {
    0: "Initiate",
    1: "Apprentice I",
    2: "Apprentice II",
    3: "Apprentice III",
    4: "Apprentice IV",
    5: "Guru I",
    6: "Guru II",
    7: "Master",
    8: "Enlightened",
    9: "Burned",
}
SRS_BUCKET_RANGES = {
    "Apprentice": (1, 4),
    "Guru": (5, 6),
    "Master": (7, 7),
    "Enlightened": (8, 8),
    "Burned": (9, 9),
}
SRS_COLORS = {
    "Apprentice": "magenta",
    "Guru": "cyan",
    "Master": "blue",
    "Enlightened": "yellow",
    "Burned": "bright_black",
}

console = Console()


# ---------------------------------------------------------------------------
# API layer
# ---------------------------------------------------------------------------

def wanikani_get(path: str) -> dict:
    """Single GET request to WaniKani API v2."""
    url = path if path.startswith("http") else f"{BASE_URL}{path}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {API_KEY}"}, timeout=30)
    if resp.status_code == 401:
        console.print("[red]Error: Invalid WaniKani API key.[/red]")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def wanikani_get_all(path: str) -> list[dict]:
    """Paginated GET — follows pages.next_url, returns flattened data list."""
    items = []
    url = f"{BASE_URL}{path}"
    while url:
        result = wanikani_get(url)
        items.extend(result.get("data", []))
        url = result.get("pages", {}).get("next_url")
        if url:
            print(".", end="", flush=True)
    if items:
        print()  # newline after dots
    return items


def fetch_user() -> dict:
    return wanikani_get("/user")["data"]


def fetch_summary() -> dict:
    return wanikani_get("/summary")["data"]


def fetch_assignments_kanji() -> list[dict]:
    console.print("  Fetching kanji assignments...", end="")
    return wanikani_get_all("/assignments?subject_types=kanji")


def fetch_review_statistics_kanji() -> list[dict]:
    console.print("  Fetching review statistics...", end="")
    return wanikani_get_all("/review_statistics?subject_types=kanji")


def fetch_level_progressions() -> list[dict]:
    console.print("  Fetching level progressions...", end="")
    return wanikani_get_all("/level_progressions")


def fetch_assignments_vocabulary() -> list[dict]:
    console.print("  Fetching vocabulary assignments...", end="")
    return wanikani_get_all("/assignments?subject_types=vocabulary")


def fetch_review_statistics_vocabulary() -> list[dict]:
    console.print("  Fetching vocabulary review statistics...", end="")
    return wanikani_get_all("/review_statistics?subject_types=vocabulary")


def fetch_subjects_kanji(refresh: bool = False) -> list[dict]:
    """Fetch kanji subjects, using cache when available."""
    if not refresh:
        cached = load_subjects_cache()
        if cached is not None:
            console.print(f"  Using cached subjects ({len(cached)} kanji)")
            return cached
    console.print("  Fetching kanji subjects (this may take a moment)...", end="")
    subjects = wanikani_get_all("/subjects?types=kanji")
    save_subjects_cache(subjects)
    return subjects


# ---------------------------------------------------------------------------
# Cache layer
# ---------------------------------------------------------------------------

def load_subjects_cache() -> list[dict] | None:
    if not os.path.exists(SUBJECTS_CACHE_PATH):
        return None
    try:
        with open(SUBJECTS_CACHE_PATH) as f:
            data = json.load(f)
        cached_at = datetime.datetime.fromisoformat(data["_cached_at"])
        age = datetime.datetime.now() - cached_at
        if age.days >= CACHE_MAX_AGE_DAYS:
            return None
        return data["subjects"]
    except (KeyError, json.JSONDecodeError, ValueError):
        return None


def save_subjects_cache(subjects: list[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SUBJECTS_CACHE_PATH, "w") as f:
        json.dump({
            "_cached_at": datetime.datetime.now().isoformat(),
            "subjects": subjects,
        }, f)
    console.print(f"  Cached {len(subjects)} subjects to {SUBJECTS_CACHE_PATH}")


# ---------------------------------------------------------------------------
# History / snapshot layer
# ---------------------------------------------------------------------------

def load_history() -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    try:
        with open(HISTORY_PATH) as f:
            data = json.load(f)
        return data.get("snapshots", [])
    except (json.JSONDecodeError, ValueError):
        return []


def save_snapshot(snapshot: dict):
    """Append snapshot to history, deduplicating by date."""
    snapshots = load_history()
    today = snapshot["date"]
    snapshots = [s for s in snapshots if s["date"] != today]
    snapshots.append(snapshot)
    snapshots.sort(key=lambda s: s["date"])
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_PATH, "w") as f:
        json.dump({"snapshots": snapshots}, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Analysis layer
# ---------------------------------------------------------------------------

def compute_srs_distribution(assignments: list[dict]) -> dict:
    buckets = {name: 0 for name in SRS_BUCKET_RANGES}
    buckets["Initiate"] = 0
    total = 0
    for a in assignments:
        stage = a["data"]["srs_stage"]
        total += 1
        if stage == 0:
            buckets["Initiate"] += 1
            continue
        for name, (lo, hi) in SRS_BUCKET_RANGES.items():
            if lo <= stage <= hi:
                buckets[name] += 1
                break
    learned = sum(buckets[b] for b in ("Guru", "Master", "Enlightened", "Burned"))
    in_progress = buckets["Apprentice"]
    return {
        "buckets": buckets,
        "total": total,
        "learned": learned,
        "in_progress": in_progress,
    }


def compute_accuracy(review_stats: list[dict]) -> dict:
    m_correct = m_incorrect = r_correct = r_incorrect = 0
    for rs in review_stats:
        d = rs["data"]
        m_correct += d["meaning_correct"]
        m_incorrect += d["meaning_incorrect"]
        r_correct += d["reading_correct"]
        r_incorrect += d["reading_incorrect"]
    m_total = m_correct + m_incorrect
    r_total = r_correct + r_incorrect
    total = m_total + r_total
    return {
        "meaning_pct": (m_correct / m_total * 100) if m_total else 0,
        "reading_pct": (r_correct / r_total * 100) if r_total else 0,
        "overall_pct": ((m_correct + r_correct) / total * 100) if total else 0,
        "total_reviews": total,
    }


def compute_pace(level_progressions: list[dict]) -> dict:
    completed = []
    for lp in level_progressions:
        d = lp["data"]
        started = d.get("started_at")
        passed = d.get("passed_at")
        if started and passed:
            start_dt = datetime.datetime.fromisoformat(started.replace("Z", "+00:00"))
            pass_dt = datetime.datetime.fromisoformat(passed.replace("Z", "+00:00"))
            days = (pass_dt - start_dt).total_seconds() / 86400
            completed.append({"level": d["level"], "days": round(days, 1)})

    if not completed:
        return {"completed": [], "avg": None, "recent_avg": None,
                "fastest": None, "slowest": None, "std_dev": None}

    days_list = [c["days"] for c in completed]
    avg = statistics.mean(days_list)
    std_dev = statistics.stdev(days_list) if len(days_list) >= 2 else 0
    recent = completed[-5:]
    recent_avg = statistics.mean([c["days"] for c in recent])
    fastest = min(completed, key=lambda c: c["days"])
    slowest = max(completed, key=lambda c: c["days"])

    return {
        "completed": completed,
        "avg": round(avg, 1),
        "recent_avg": round(recent_avg, 1),
        "fastest": fastest,
        "slowest": slowest,
        "std_dev": round(std_dev, 1),
    }


def compute_jlpt_coverage(assignments: list[dict], subjects: list[dict]) -> dict:
    """Map each kanji to a JLPT level via its WaniKani level, count learned."""
    # Build subject_id -> WK level map
    subject_level_map = {}
    for s in subjects:
        subject_level_map[s["id"]] = s["data"]["level"]

    # Assign each kanji to a JLPT bucket based on WK level
    jlpt_counts = {}
    for jlpt, (lo, hi) in JLPT_LEVEL_RANGES.items():
        jlpt_counts[jlpt] = {"total": 0, "learned": 0, "in_progress": 0}

    # Count total kanji per JLPT level from subjects
    for s in subjects:
        wk_level = s["data"]["level"]
        for jlpt, (lo, hi) in JLPT_LEVEL_RANGES.items():
            if lo <= wk_level <= hi:
                jlpt_counts[jlpt]["total"] += 1
                break

    # Count user progress from assignments
    for a in assignments:
        sid = a["data"]["subject_id"]
        wk_level = subject_level_map.get(sid)
        if wk_level is None:
            continue
        stage = a["data"]["srs_stage"]
        for jlpt, (lo, hi) in JLPT_LEVEL_RANGES.items():
            if lo <= wk_level <= hi:
                if stage >= 5:  # Guru+
                    jlpt_counts[jlpt]["learned"] += 1
                elif stage >= 1:
                    jlpt_counts[jlpt]["in_progress"] += 1
                break

    # Compute percentages
    for jlpt in jlpt_counts:
        total = jlpt_counts[jlpt]["total"]
        learned = jlpt_counts[jlpt]["learned"]
        jlpt_counts[jlpt]["pct"] = round(learned / total * 100, 1) if total else 0

    return jlpt_counts


def compute_level_up_estimate(user_level: int, assignments: list[dict],
                              subjects: list[dict], accuracy: dict) -> dict:
    """Estimate time to next level based on current-level kanji SRS spread.

    WaniKani requires 90% of a level's kanji to reach Guru (stage 5+) to level up.
    Uses each item's SRS stage and available_at to project when the threshold is met.
    """
    # Minimum hours between SRS stages (assuming correct answer)
    SRS_INTERVALS_HOURS = {
        1: 4,    # Apprentice I  → II
        2: 8,    # Apprentice II → III
        3: 23,   # Apprentice III → IV
        4: 47,   # Apprentice IV → Guru I
    }

    # Build set of current-level kanji subject IDs
    current_level_kanji_ids = set()
    for s in subjects:
        if s["data"]["level"] == user_level:
            current_level_kanji_ids.add(s["id"])

    if not current_level_kanji_ids:
        return {"status": "no_data"}

    # Gather current-level kanji assignments with SRS info
    now = datetime.datetime.now(datetime.timezone.utc)
    items = []
    for a in assignments:
        sid = a["data"]["subject_id"]
        if sid not in current_level_kanji_ids:
            continue
        stage = a["data"]["srs_stage"]
        available_at_str = a["data"].get("available_at")
        available_at = None
        if available_at_str:
            available_at = datetime.datetime.fromisoformat(
                available_at_str.replace("Z", "+00:00"))
        items.append({
            "subject_id": sid,
            "srs_stage": stage,
            "available_at": available_at,
        })

    total_kanji = len(current_level_kanji_ids)
    assigned = len(items)
    not_started = total_kanji - assigned
    guru_needed = int(total_kanji * 0.9)  # 90% threshold

    # Count already at Guru+
    already_guru = sum(1 for it in items if it["srs_stage"] >= 5)

    if already_guru >= guru_needed:
        return {
            "status": "ready",
            "total_kanji": total_kanji,
            "guru_needed": guru_needed,
            "already_guru": already_guru,
        }

    still_needed = guru_needed - already_guru

    # Factor in accuracy: on average, an incorrect answer adds ~1 extra review
    # cycle at the current stage. We model this as a multiplier on expected time.
    reading_acc = accuracy.get("reading_pct", 85) / 100
    meaning_acc = accuracy.get("meaning_pct", 95) / 100
    # Both meaning AND reading must be correct to advance; probability of advancing:
    advance_prob = reading_acc * meaning_acc
    # Expected reviews to advance = 1 / advance_prob
    # Each failed review also demotes the item, costing roughly one extra interval.
    # Simplified: multiply ideal time by 1/advance_prob
    accuracy_multiplier = 1.0 / advance_prob if advance_prob > 0 else 2.0

    # For each non-guru item, estimate hours until it reaches stage 5
    estimates = []
    for it in items:
        stage = it["srs_stage"]
        if stage >= 5:
            continue  # already guru

        # Calculate ideal hours from current stage to Guru
        ideal_hours = 0
        for s in range(max(stage, 1), 5):
            ideal_hours += SRS_INTERVALS_HOURS[s]

        # If stage 0 (not yet started lessons), add first interval
        if stage == 0:
            ideal_hours = sum(SRS_INTERVALS_HOURS.values())  # full path

        # Apply accuracy multiplier for realistic estimate
        realistic_hours = ideal_hours * accuracy_multiplier

        # If item has a scheduled review, use that as the start point
        if it["available_at"] and it["available_at"] > now:
            wait_hours = (it["available_at"] - now).total_seconds() / 3600
            # The next review covers the current stage transition
            remaining_stages_hours = 0
            for s in range(max(stage + 1, 1), 5):
                remaining_stages_hours += SRS_INTERVALS_HOURS.get(s, 0)
            realistic_hours = wait_hours + remaining_stages_hours * accuracy_multiplier
        elif stage == 0:
            # Not yet in lessons — unknown when they'll be unlocked
            realistic_hours = ideal_hours * accuracy_multiplier

        estimates.append({
            "subject_id": it["subject_id"],
            "srs_stage": stage,
            "hours_to_guru": round(realistic_hours, 1),
        })

    # Items not yet assigned (locked) — assume they start from scratch once unlocked
    for _ in range(not_started):
        full_path_hours = sum(SRS_INTERVALS_HOURS.values()) * accuracy_multiplier
        estimates.append({
            "subject_id": None,
            "srs_stage": -1,
            "hours_to_guru": round(full_path_hours, 1),
        })

    # Sort by time to guru — the level-up happens when the Nth fastest item hits guru
    estimates.sort(key=lambda e: e["hours_to_guru"])

    # We need `still_needed` more items to reach guru
    if still_needed <= len(estimates):
        level_up_hours = estimates[still_needed - 1]["hours_to_guru"]
    else:
        level_up_hours = estimates[-1]["hours_to_guru"] if estimates else 0

    level_up_date = now + datetime.timedelta(hours=level_up_hours)

    # SRS stage breakdown for current level
    stage_counts = {}
    for it in items:
        s = it["srs_stage"]
        name = SRS_STAGE_NAMES.get(s, f"Stage {s}")
        stage_counts[name] = stage_counts.get(name, 0) + 1

    return {
        "status": "in_progress",
        "total_kanji": total_kanji,
        "guru_needed": guru_needed,
        "already_guru": already_guru,
        "still_needed": still_needed,
        "not_started": not_started,
        "stage_counts": stage_counts,
        "accuracy_multiplier": round(accuracy_multiplier, 2),
        "optimistic_hours": round(level_up_hours / accuracy_multiplier, 1),
        "realistic_hours": round(level_up_hours, 1),
        "optimistic_date": (now + datetime.timedelta(
            hours=level_up_hours / accuracy_multiplier)).isoformat(),
        "realistic_date": level_up_date.isoformat(),
        "items": estimates[:still_needed],  # the bottleneck items
    }


def compute_predictions(user_level: int, pace: dict, jlpt_coverage: dict,
                        days_studied: int) -> dict:
    predictions = {}
    today = datetime.date.today()

    # --- Approach A: Level-based ---
    level_based = {}
    for target_name, target_level in [("N2", 48), ("N1", 60)]:
        remaining = target_level - user_level
        if remaining <= 0:
            level_based[target_name] = {"status": "reached", "level": target_level}
            continue
        if pace["avg"] is None:
            level_based[target_name] = {"status": "insufficient_data"}
            continue

        realistic_days = remaining * pace["recent_avg"]
        optimistic_pace = max(pace["avg"] - pace["std_dev"], pace["fastest"]["days"])
        pessimistic_pace = min(pace["avg"] + pace["std_dev"], pace["slowest"]["days"])
        optimistic_days = remaining * optimistic_pace
        pessimistic_days = remaining * pessimistic_pace

        level_based[target_name] = {
            "status": "projected",
            "remaining_levels": remaining,
            "optimistic": {
                "days": round(optimistic_days),
                "date": (today + datetime.timedelta(days=optimistic_days)).isoformat(),
                "pace": round(optimistic_pace, 1),
            },
            "realistic": {
                "days": round(realistic_days),
                "date": (today + datetime.timedelta(days=realistic_days)).isoformat(),
                "pace": pace["recent_avg"],
            },
            "pessimistic": {
                "days": round(pessimistic_days),
                "date": (today + datetime.timedelta(days=pessimistic_days)).isoformat(),
                "pace": round(pessimistic_pace, 1),
            },
        }
    predictions["level_based"] = level_based

    # --- Approach B: Kanji coverage rate ---
    coverage_based = {}
    total_learned = sum(jlpt_coverage[j]["learned"] for j in jlpt_coverage)
    kanji_per_day = total_learned / days_studied if days_studied > 0 else 0

    for target_name in ("N2", "N1"):
        # N2 = need all kanji through N2 range; N1 = need all
        target_jlpts = {
            "N2": ["N5", "N4", "N3", "N2"],
            "N1": ["N5", "N4", "N3", "N2", "N1"],
        }[target_name]
        needed = sum(jlpt_coverage[j]["total"] for j in target_jlpts)
        learned = sum(jlpt_coverage[j]["learned"] for j in target_jlpts)
        remaining = needed - learned

        if remaining <= 0:
            coverage_based[target_name] = {
                "status": "reached", "learned": learned, "needed": needed
            }
            continue
        if kanji_per_day <= 0:
            coverage_based[target_name] = {"status": "insufficient_data"}
            continue

        est_days = remaining / kanji_per_day
        coverage_based[target_name] = {
            "status": "projected",
            "learned": learned,
            "needed": needed,
            "remaining": remaining,
            "kanji_per_day": round(kanji_per_day, 2),
            "est_days": round(est_days),
            "est_date": (today + datetime.timedelta(days=est_days)).isoformat(),
        }
    predictions["coverage_based"] = coverage_based

    return predictions


def compute_sessions_and_streaks(review_stats: list[dict],
                                  assignments: list[dict]) -> dict:
    """Compute daily session counts and streak data from activity timestamps.

    Uses data_updated_at from review_statistics (each item's last review time)
    plus started_at/passed_at from assignments to build activity timeline.
    A 'session' is a cluster of activity timestamps within 30 min of each other.
    """
    SESSION_GAP_MINUTES = 30

    # Collect all activity timestamps
    timestamps = []
    for rs in review_stats:
        ts_str = rs.get("data_updated_at")
        if ts_str:
            dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            timestamps.append(dt)
        created = rs["data"].get("created_at")
        if created:
            dt = datetime.datetime.fromisoformat(created.replace("Z", "+00:00"))
            timestamps.append(dt)

    for a in assignments:
        for field in ("started_at", "passed_at"):
            ts_str = a["data"].get(field)
            if ts_str:
                dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                timestamps.append(dt)

    if not timestamps:
        return {
            "sessions_per_day_avg": 0,
            "sessions_per_day_recent_7d": 0,
            "daily_sessions": {},
            "current_streak": 0,
            "longest_streak": 0,
            "total_review_days": 0,
        }

    timestamps.sort()

    # Group by UTC date and count sessions per day
    daily_activity = defaultdict(list)
    for ts in timestamps:
        date_str = ts.date().isoformat()
        daily_activity[date_str].append(ts)

    daily_sessions = {}
    for date_str, day_timestamps in daily_activity.items():
        day_timestamps.sort()
        sessions = 1
        for i in range(1, len(day_timestamps)):
            gap = (day_timestamps[i] - day_timestamps[i - 1]).total_seconds() / 60
            if gap > SESSION_GAP_MINUTES:
                sessions += 1
        daily_sessions[date_str] = sessions

    # Average sessions per day (across days that had activity)
    total_review_days = len(daily_sessions)
    sessions_per_day_avg = (
        sum(daily_sessions.values()) / total_review_days
        if total_review_days else 0
    )

    # Recent 7-day average
    today = datetime.date.today()
    recent_7d_sessions = []
    for i in range(7):
        d = (today - datetime.timedelta(days=i)).isoformat()
        if d in daily_sessions:
            recent_7d_sessions.append(daily_sessions[d])
    sessions_per_day_recent_7d = (
        sum(recent_7d_sessions) / len(recent_7d_sessions)
        if recent_7d_sessions else 0
    )

    # Streaks — consecutive calendar days with at least 1 activity
    review_dates = sorted(daily_activity.keys())
    review_date_set = set(review_dates)

    # Current streak (counting back from today)
    current_streak = 0
    d = today
    while d.isoformat() in review_date_set:
        current_streak += 1
        d -= datetime.timedelta(days=1)

    # Longest streak
    longest_streak = 0
    streak = 0
    if review_dates:
        prev = datetime.date.fromisoformat(review_dates[0])
        streak = 1
        for ds in review_dates[1:]:
            cur = datetime.date.fromisoformat(ds)
            if (cur - prev).days == 1:
                streak += 1
            else:
                longest_streak = max(longest_streak, streak)
                streak = 1
            prev = cur
        longest_streak = max(longest_streak, streak)

    return {
        "sessions_per_day_avg": round(sessions_per_day_avg, 2),
        "sessions_per_day_recent_7d": round(sessions_per_day_recent_7d, 2),
        "daily_sessions": daily_sessions,
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_review_days": total_review_days,
    }


# ---------------------------------------------------------------------------
# Display layer
# ---------------------------------------------------------------------------

def format_date(iso_date: str) -> str:
    d = datetime.date.fromisoformat(iso_date)
    return d.strftime("%b %Y")


def format_duration(days: int) -> str:
    years = days // 365
    months = (days % 365) // 30
    if years and months:
        return f"{years}y {months}m"
    if years:
        return f"{years}y"
    return f"{months}m"


def accuracy_color(pct: float) -> str:
    if pct >= 90:
        return "green"
    if pct >= 80:
        return "yellow"
    return "red"


def render_level_up_estimate(estimate: dict, user_level: int):
    """Render the time-to-next-level panel."""
    if estimate["status"] == "no_data":
        console.print(Panel("[dim]No kanji data for current level[/dim]",
                            title=f"[bold]Level {user_level} → {user_level + 1}[/bold]",
                            border_style="bright_blue"))
        return

    if estimate["status"] == "ready":
        console.print(Panel(
            f"[bold green]Ready to level up![/bold green]  "
            f"{estimate['already_guru']}/{estimate['guru_needed']} kanji at Guru+",
            title=f"[bold]Level {user_level} → {user_level + 1}[/bold]",
            border_style="green"))
        return

    e = estimate

    # Stage breakdown mini-table
    stage_table = Table(show_header=False, box=None, padding=(0, 2))
    stage_table.add_column("Stage", style="bold", min_width=14)
    stage_table.add_column("Count", justify="right", min_width=4)
    stage_order = ["Initiate", "Apprentice I", "Apprentice II",
                   "Apprentice III", "Apprentice IV", "Guru I", "Guru II",
                   "Master", "Enlightened", "Burned"]
    for stage_name in stage_order:
        count = e["stage_counts"].get(stage_name, 0)
        if count == 0:
            continue
        if "Apprentice" in stage_name:
            color = "magenta"
        elif "Guru" in stage_name or stage_name in ("Master", "Enlightened", "Burned"):
            color = "cyan"
        else:
            color = "dim"
        stage_table.add_row(f"[{color}]{stage_name}[/{color}]", str(count))

    # Time estimates
    opt_hours = e["optimistic_hours"]
    real_hours = e["realistic_hours"]
    opt_date = datetime.datetime.fromisoformat(e["optimistic_date"])
    real_date = datetime.datetime.fromisoformat(e["realistic_date"])

    def fmt_hours(h):
        if h < 24:
            return f"{h:.0f}h"
        days = h / 24
        if days < 2:
            return f"{days:.1f}d"
        return f"{days:.0f}d"

    progress_pct = e["already_guru"] / e["guru_needed"] * 100
    filled = int(progress_pct / 100 * 20)
    bar = f"[green]{'█' * filled}[/green][dim]{'░' * (20 - filled)}[/dim]"

    text_lines = [
        f"Kanji: {bar}  [bold]{e['already_guru']}[/bold]/{e['guru_needed']} at Guru+ "
        f"([yellow]{e['still_needed']}[/yellow] more needed)",
    ]
    if e["not_started"] > 0:
        text_lines.append(f"  [dim]{e['not_started']} kanji not yet in lessons[/dim]")
    text_lines.append("")
    text_lines.append(
        f"[green]Optimistic[/green] (perfect reviews): "
        f"[bold]{fmt_hours(opt_hours)}[/bold]  →  {opt_date.strftime('%b %d %H:%M')}"
    )
    text_lines.append(
        f"[yellow]Realistic[/yellow]  ({e['accuracy_multiplier']:.2f}x accuracy adj): "
        f"[bold]{fmt_hours(real_hours)}[/bold]  →  {real_date.strftime('%b %d %H:%M')}"
    )

    console.print(Panel(
        "\n".join(text_lines),
        title=f"[bold]Level {user_level} → {user_level + 1}  ⏱  Time to Level Up[/bold]",
        border_style="bright_blue",
    ))
    console.print(stage_table)
    console.print()


def render_report(user, summary, srs, accuracy, vocab_srs, vocab_accuracy,
                  pace, jlpt, predictions, level_up, days_studied):
    console.print()

    # --- Profile ---
    level = user["level"]
    max_level = user.get("subscription", {}).get("max_level_granted", 3)
    sub_type = user.get("subscription", {}).get("type", "free")
    reviews_available = sum(len(r["subject_ids"]) for r in summary.get("reviews", []))
    lessons_available = sum(len(l["subject_ids"]) for l in summary.get("lessons", []))

    profile_text = (
        f"[bold]Level {level}[/bold] / 60  |  "
        f"{days_studied} days studied  |  "
        f"Subscription: {sub_type} (max level {max_level})\n"
        f"Kanji: [cyan]{srs['learned']}[/cyan] learned  |  "
        f"Vocab: [magenta]{vocab_srs['learned']}[/magenta] learned\n"
        f"Pending: [yellow]{reviews_available}[/yellow] reviews, "
        f"[cyan]{lessons_available}[/cyan] lessons"
    )
    console.print(Panel(profile_text, title="[bold]Profile[/bold]", border_style="bright_blue"))

    # --- Level Up Estimate ---
    render_level_up_estimate(level_up, level)

    # --- SRS Breakdown ---
    srs_table = Table(title="SRS Breakdown (Kanji)", show_header=True, header_style="bold")
    srs_table.add_column("Stage", style="bold", min_width=12)
    srs_table.add_column("Count", justify="right", min_width=6)
    srs_table.add_column("Bar", min_width=30)

    max_count = max(srs["buckets"].values()) if srs["buckets"] else 1
    for name in ["Apprentice", "Guru", "Master", "Enlightened", "Burned"]:
        count = srs["buckets"][name]
        bar_len = int(count / max_count * 25) if max_count > 0 else 0
        color = SRS_COLORS[name]
        bar = f"[{color}]{'█' * bar_len}[/{color}]"
        srs_table.add_row(f"[{color}]{name}[/{color}]", str(count), bar)

    srs_table.add_section()
    srs_table.add_row("Learned (Guru+)", f"[bold]{srs['learned']}[/bold]", "")
    srs_table.add_row("In Progress", str(srs["in_progress"]), "")
    srs_table.add_row("Not Started", str(srs["buckets"]["Initiate"]), "")
    console.print(srs_table)
    console.print()

    # --- Vocab SRS Summary ---
    vocab_table = Table(title="Vocabulary Summary", show_header=True, header_style="bold")
    vocab_table.add_column("Metric", style="bold", min_width=16)
    vocab_table.add_column("Count", justify="right", min_width=8)
    vocab_table.add_row("Learned (Guru+)", f"[bold magenta]{vocab_srs['learned']}[/bold magenta]")
    vocab_table.add_row("In Progress", str(vocab_srs["in_progress"]))
    vocab_table.add_row("Not Started", str(vocab_srs["buckets"]["Initiate"]))
    vocab_table.add_row("Total", str(vocab_srs["total"]))
    console.print(vocab_table)
    console.print()

    # --- Accuracy ---
    acc_table = Table(title="Review Accuracy", show_header=True, header_style="bold")
    acc_table.add_column("Type", style="bold")
    acc_table.add_column("Accuracy", justify="right")
    acc_table.add_column("Total Reviews", justify="right")

    m_pct = accuracy["meaning_pct"]
    r_pct = accuracy["reading_pct"]
    o_pct = accuracy["overall_pct"]
    acc_table.add_row("Meaning", f"[{accuracy_color(m_pct)}]{m_pct:.1f}%[/{accuracy_color(m_pct)}]", "")
    acc_table.add_row("Reading", f"[{accuracy_color(r_pct)}]{r_pct:.1f}%[/{accuracy_color(r_pct)}]", "")
    acc_table.add_row(
        "[bold]Overall[/bold]",
        f"[bold {accuracy_color(o_pct)}]{o_pct:.1f}%[/bold {accuracy_color(o_pct)}]",
        str(accuracy["total_reviews"]),
    )
    acc_table.add_section()
    vm_pct = vocab_accuracy["meaning_pct"]
    vr_pct = vocab_accuracy["reading_pct"]
    vo_pct = vocab_accuracy["overall_pct"]
    acc_table.add_row("Vocab Meaning", f"[{accuracy_color(vm_pct)}]{vm_pct:.1f}%[/{accuracy_color(vm_pct)}]", "")
    acc_table.add_row("Vocab Reading", f"[{accuracy_color(vr_pct)}]{vr_pct:.1f}%[/{accuracy_color(vr_pct)}]", "")
    acc_table.add_row(
        "[bold]Vocab Overall[/bold]",
        f"[bold {accuracy_color(vo_pct)}]{vo_pct:.1f}%[/bold {accuracy_color(vo_pct)}]",
        str(vocab_accuracy["total_reviews"]),
    )
    console.print(acc_table)
    console.print()

    # --- Pace ---
    if pace["avg"] is not None:
        fastest = pace["fastest"]
        slowest = pace["slowest"]
        pace_text = (
            f"Average: [bold]{pace['avg']}[/bold] days/level  |  "
            f"Recent (last {min(5, len(pace['completed']))}): [bold]{pace['recent_avg']}[/bold] days/level\n"
            f"Fastest: Level {fastest['level']} in {fastest['days']} days  |  "
            f"Slowest: Level {slowest['level']} in {slowest['days']} days  |  "
            f"Std Dev: ±{pace['std_dev']} days"
        )
    else:
        pace_text = "[dim]Not enough completed levels for pace analysis[/dim]"
    console.print(Panel(pace_text, title="[bold]Pace[/bold]", border_style="bright_blue"))

    # --- JLPT Progress ---
    jlpt_table = Table(title="JLPT Kanji Coverage", show_header=True, header_style="bold")
    jlpt_table.add_column("Level", style="bold", min_width=5)
    jlpt_table.add_column("Learned", justify="right")
    jlpt_table.add_column("Total", justify="right")
    jlpt_table.add_column("Coverage", justify="right")
    jlpt_table.add_column("Progress", min_width=22)

    for jlpt_level in ["N5", "N4", "N3", "N2", "N1"]:
        c = jlpt[jlpt_level]
        pct = c["pct"]
        filled = int(pct / 100 * 20)
        bar = f"[green]{'█' * filled}[/green][dim]{'░' * (20 - filled)}[/dim]"
        pct_color = "green" if pct >= 90 else ("yellow" if pct >= 50 else "white")
        jlpt_table.add_row(
            jlpt_level,
            str(c["learned"]),
            str(c["total"]),
            f"[{pct_color}]{pct:.1f}%[/{pct_color}]",
            bar,
        )
    console.print(jlpt_table)
    console.print()

    # --- Predictions ---
    pred_table = Table(title="N2 / N1 Predictions", show_header=True, header_style="bold",
                       title_style="bold bright_blue")
    pred_table.add_column("Target", style="bold")
    pred_table.add_column("Optimistic", justify="center", style="green")
    pred_table.add_column("Realistic", justify="center", style="yellow")
    pred_table.add_column("Pessimistic", justify="center", style="red")

    lb = predictions["level_based"]
    for target in ("N2", "N1"):
        p = lb[target]
        if p["status"] == "reached":
            pred_table.add_row(f"{target} (level-based)", "Reached!", "Reached!", "Reached!")
        elif p["status"] == "insufficient_data":
            pred_table.add_row(f"{target} (level-based)", "—", "—", "—")
        else:
            pred_table.add_row(
                f"{target} (Lv {JLPT_LEVEL_TARGETS[target]})",
                f"{format_date(p['optimistic']['date'])}\n({format_duration(p['optimistic']['days'])})",
                f"{format_date(p['realistic']['date'])}\n({format_duration(p['realistic']['days'])})",
                f"{format_date(p['pessimistic']['date'])}\n({format_duration(p['pessimistic']['days'])})",
            )
    console.print(pred_table)

    # Coverage-based supplementary
    cb = predictions["coverage_based"]
    cov_lines = []
    for target in ("N2", "N1"):
        p = cb[target]
        if p["status"] == "reached":
            cov_lines.append(f"  {target}: All {p['needed']} kanji learned!")
        elif p["status"] == "insufficient_data":
            cov_lines.append(f"  {target}: Not enough data")
        else:
            cov_lines.append(
                f"  {target}: {p['learned']}/{p['needed']} kanji "
                f"({p['remaining']} remaining at {p['kanji_per_day']}/day "
                f"→ ~{format_date(p['est_date'])})"
            )
    console.print(Panel(
        "\n".join(cov_lines),
        title="[bold]Coverage-Based Estimate[/bold]",
        subtitle=f"[dim]Rate: {cb.get('N1', cb.get('N2', {})).get('kanji_per_day', '?')} kanji/day avg[/dim]",
        border_style="bright_blue",
    ))
    console.print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="WaniKani progress tracker with JLPT predictions")
    parser.add_argument("--refresh", action="store_true", help="Force refresh subjects cache")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of report")
    args = parser.parse_args()

    if not API_KEY:
        console.print("[red]Error: WANIKANI_API_KEY not set in .env[/red]")
        sys.exit(1)

    console.print("[bold bright_blue]WaniKani Progress Tracker[/bold bright_blue]")
    console.print("Fetching data from WaniKani API...")

    user = fetch_user()
    summary = fetch_summary()
    assignments = fetch_assignments_kanji()
    review_stats = fetch_review_statistics_kanji()
    vocab_assignments = fetch_assignments_vocabulary()
    vocab_review_stats = fetch_review_statistics_vocabulary()
    level_progs = fetch_level_progressions()
    subjects = fetch_subjects_kanji(refresh=args.refresh)

    today = datetime.date.today()
    start_date = _parse_start_date()
    if start_date is None:
        started_at = user.get("started_at", "")
        if started_at:
            start_date = datetime.datetime.fromisoformat(started_at.replace("Z", "+00:00")).date()
        else:
            start_date = today
    days_studied = (today - start_date).days

    console.print("Analyzing...")
    srs = compute_srs_distribution(assignments)
    accuracy = compute_accuracy(review_stats)
    vocab_srs = compute_srs_distribution(vocab_assignments)
    vocab_accuracy = compute_accuracy(vocab_review_stats)
    pace = compute_pace(level_progs)
    jlpt = compute_jlpt_coverage(assignments, subjects)
    level_up = compute_level_up_estimate(user["level"], assignments, subjects, accuracy)
    predictions = compute_predictions(user["level"], pace, jlpt, days_studied)
    all_review_stats = review_stats + vocab_review_stats
    all_assignments = assignments + vocab_assignments
    sessions_streaks = compute_sessions_and_streaks(all_review_stats, all_assignments)

    snapshot = {
        "date": today.isoformat(),
        "level": user["level"],
        "days_studied": days_studied,
        "kanji_learned": srs["learned"],
        "kanji_in_progress": srs["in_progress"],
        "srs": srs,
        "accuracy": accuracy,
        "vocab_learned": vocab_srs["learned"],
        "vocab_in_progress": vocab_srs["in_progress"],
        "vocab_srs": vocab_srs,
        "vocab_accuracy": vocab_accuracy,
        "pace": pace,
        "jlpt_coverage": jlpt,
        "level_up": level_up,
        "predictions": predictions,
        "sessions_streaks": sessions_streaks,
    }
    save_snapshot(snapshot)

    if args.json:
        output = {
            "user_level": user["level"],
            "days_studied": days_studied,
            "srs": srs,
            "accuracy": accuracy,
            "vocab_srs": vocab_srs,
            "vocab_accuracy": vocab_accuracy,
            "pace": pace,
            "jlpt_coverage": jlpt,
            "level_up": level_up,
            "predictions": predictions,
            "sessions_streaks": sessions_streaks,
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        render_report(user, summary, srs, accuracy, vocab_srs, vocab_accuracy,
                      pace, jlpt, predictions, level_up, days_studied)


if __name__ == "__main__":
    main()
