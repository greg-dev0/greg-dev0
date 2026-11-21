"""Generate a private-aware, repository-anonymous GitHub activity SVG."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

GRAPHQL_URL = "https://api.github.com/graphql"
BG = "#000000"
BORDER = "#263241"
TEXT = "#E6EDF3"
MUTED = "#8392A5"
ACCENT = "#307ed7"
ACCENT_BRIGHT = "#BAE6FD"
LEVEL_COLORS = ["#171E27", "#183548", "#24536D", "#367FA0", "#7DD3FC"]

QUERY = """
query ContributionActivity($from: DateTime!, $to: DateTime!) {
  viewer {
    contributionsCollection(from: $from, to: $to) {
      hasAnyRestrictedContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def fetch_contributions(token: str, start: date, end: date) -> dict[str, Any]:
    payload = {
        "query": QUERY,
        "variables": {
            "from": f"{start.isoformat()}T00:00:00Z",
            "to": f"{end.isoformat()}T23:59:59Z",
        },
    }
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "greg-dev0-activity-card",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub GraphQL request failed (HTTP {exc.code}): {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Could not reach GitHub GraphQL API: {exc.reason}") from exc

    if body.get("errors"):
        messages = "; ".join(str(item.get("message", "GraphQL error")) for item in body["errors"])
        raise RuntimeError(f"GitHub GraphQL returned an error: {messages}")
    try:
        return body["data"]["viewer"]["contributionsCollection"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("GitHub GraphQL response did not contain the contribution calendar.") from exc


def normalize_days(collection: dict[str, Any], start: date, end: date) -> dict[date, int]:
    counts: dict[date, int] = {}
    for week in collection["contributionCalendar"]["weeks"]:
        for item in week["contributionDays"]:
            day = date.fromisoformat(item["date"])
            if start <= day <= end:
                counts[day] = int(item["contributionCount"])
    current = start
    while current <= end:
        counts.setdefault(current, 0)
        current += timedelta(days=1)
    return counts


def calculate_metrics(days: dict[date, int], end: date) -> dict[str, Any]:
    ordered_dates = sorted(days)
    values = [days[day] for day in ordered_dates]

    longest = 0
    run = 0
    for value in values:
        if value > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    # A streak remains current through today even before today's contribution is made.
    index = len(ordered_dates) - 1
    if index >= 0 and ordered_dates[index] == end and days[end] == 0:
        index -= 1
    current = 0
    while index >= 0 and days[ordered_dates[index]] > 0:
        current += 1
        index -= 1

    busiest_date = max(ordered_dates, key=lambda day: (days[day], day)) if ordered_dates else None
    busiest_count = days[busiest_date] if busiest_date else 0
    return {
        "total": sum(values),
        "current_streak": current,
        "longest_streak": longest,
        "busiest_count": busiest_count,
        "busiest_date": busiest_date,
    }


def contribution_level(count: int, positive_counts: list[int]) -> int:
    if count <= 0 or not positive_counts:
        return 0
    ordered = sorted(positive_counts)
    q25 = ordered[int((len(ordered) - 1) * 0.25)]
    q50 = ordered[int((len(ordered) - 1) * 0.50)]
    q75 = ordered[int((len(ordered) - 1) * 0.75)]
    if q25 == q75:
        return 2
    if count >= q75:
        return 4
    if count >= q50:
        return 3
    if count >= q25:
        return 2
    return 1


FONT = "ui-monospace, SFMono-Regular, JetBrains Mono, Consolas, monospace"
DOT_LEVELS = ["#161B22", "#0F2A4D", "#164A8C", "#307ed7", "#7CB8FF"]


def render_svg(days: dict[date, int], start: date, end: date, metrics: dict[str, Any]) -> str:
    """Terminal-style card: window chrome, dot heatmap with glow, stat row."""
    width, height = 1000, 310
    r, pitch = 5.5, 15
    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=6 - end.weekday())
    week_count = ((grid_end - grid_start).days // 7) + 1
    grid_x, grid_y = 64, 120
    if grid_x + week_count * pitch > width - 20:
        raise RuntimeError("Activity calendar is wider than the SVG layout.")

    positives = [v for v in days.values() if v > 0]
    p = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub activity over the last 12 months</title>',
        '<desc id="desc">An anonymized contribution heatmap with aggregate totals and streak statistics. No repository names or contribution details are shown.</desc>',
        '<defs>',
        f'<linearGradient id="bar" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#161B22"/><stop offset="1" stop-color="#0B0F14"/></linearGradient>',
        f'<linearGradient id="line" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{ACCENT}"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></linearGradient>',
        '<filter id="glow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        '</defs>',
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="12" fill="#0B0F14" stroke="#21262D"/>',
        f'<path d="M0.5 12.5a12 12 0 0 1 12-12h{width-25}a12 12 0 0 1 12 12V40H0.5z" fill="url(#bar)"/>',
        '<line x1="0.5" y1="40.5" x2="999.5" y2="40.5" stroke="#21262D"/>',
        '<circle cx="24" cy="21" r="5.5" fill="#FF5F56"/><circle cx="44" cy="21" r="5.5" fill="#FFBD2E"/><circle cx="64" cy="21" r="5.5" fill="#27C93F"/>',
        f'<text x="28" y="72" fill="{ACCENT}" font-family="{FONT}" font-size="14" font-weight="700">$</text>',
        f'<text x="46" y="72" fill="{TEXT}" font-family="{FONT}" font-size="14">git log --author=me --since="last 12 months"</text>',
        '<rect x="28" y="82" width="944" height="1.5" fill="url(#line)" opacity="0.7"/>',
    ]

    seen: set[tuple[int, int]] = set()
    cur = start
    while cur <= end:
        if cur.day == 1 and (cur.year, cur.month) not in seen:
            seen.add((cur.year, cur.month))
            x = grid_x + ((cur - grid_start).days // 7) * pitch - r
            p.append(f'<text x="{x}" y="108" fill="{MUTED}" font-family="{FONT}" font-size="10">{escape(cur.strftime("%b").lower())}</text>')
        cur += timedelta(days=1)
    for label, row in (("mon", 0), ("wed", 2), (" fri", 4)):
        p.append(f'<text x="28" y="{grid_y + row * pitch + 3.5}" fill="{MUTED}" font-family="{FONT}" font-size="10">{label.strip()}</text>')

    total_days = (grid_end - grid_start).days + 1
    for offset in range(total_days):
        day = grid_start + timedelta(days=offset)
        cx = grid_x + (offset // 7) * pitch
        cy = grid_y + day.weekday() * pitch
        if day < start or day > end:
            continue
        count = days.get(day, 0)
        level = contribution_level(count, positives)
        tip = escape(f"{day.isoformat()}: {count} contributions")
        extra = ' filter="url(#glow)"' if level >= 3 else ""
        p.append(f'<circle cx="{cx}" cy="{cy}" r="{r if level else r - 1}" fill="{DOT_LEVELS[level]}"{extra}><title>{tip}</title></circle>')

    # legend
    ly = 68
    lx = width - 28 - 30
    p.append(f'<text x="{lx - 5 * 14 - 8}" y="{ly + 3}" text-anchor="end" fill="{MUTED}" font-family="{FONT}" font-size="10">less</text>')
    for i, c in enumerate(DOT_LEVELS):
        p.append(f'<circle cx="{lx - 5 * 14 + i * 14}" cy="{ly}" r="4.5" fill="{c}"/>')
    p.append(f'<text x="{lx - 5 * 14 + 5 * 14 - 4}" y="{ly + 3}" fill="{MUTED}" font-family="{FONT}" font-size="10">more</text>')

    busiest = metrics["busiest_date"].isoformat() if metrics["busiest_date"] else "n/a"
    items = [
        (f'{metrics["total"]:,}', "contributions", ACCENT),
        (f'{metrics["current_streak"]}d', "current streak", ACCENT_BRIGHT),
        (f'{metrics["longest_streak"]}d', "longest streak", ACCENT),
        (str(metrics["busiest_count"]), f"busiest day · {busiest}", ACCENT_BRIGHT),
    ]
    for i, (value, label, color) in enumerate(items):
        x = 28 + i * 236
        if i:
            p.append(f'<line x1="{x-16}" y1="246" x2="{x-16}" y2="290" stroke="#21262D"/>')
        p.append(f'<text x="{x}" y="270" fill="{color}" font-family="{FONT}" font-size="26" font-weight="700">{escape(value)}</text>')
        p.append(f'<text x="{x}" y="288" fill="{MUTED}" font-family="{FONT}" font-size="10">{escape(label)}</text>')
    p.append("</svg>")
    return "\n".join(p)


def render_svg_legacy(days: dict[date, int], start: date, end: date, metrics: dict[str, Any]) -> str:
    width, height = 1000, 270
    cell, gap = 14, 5
    pitch = cell + gap
    grid_start = start - timedelta(days=start.weekday())
    grid_end = end + timedelta(days=6 - end.weekday())
    week_count = ((grid_end - grid_start).days // 7) + 1
    if week_count * pitch > width - 88:
        raise RuntimeError("Activity calendar is wider than the SVG layout.")

    positives = [value for value in days.values() if value > 0]
    grid_x, grid_y = 50, 88
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
        '<title id="title">GitHub activity over the last 12 months</title>',
        '<desc id="desc">An anonymized contribution heatmap with aggregate totals and streak statistics. No repository names or contribution details are shown.</desc>',
        f'<rect x="0.5" y="0.5" width="{width-1}" height="{height-1}" rx="14" fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="26" y="34" fill="{TEXT}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="14" font-weight="700" letter-spacing="2">ACTIVITY · LAST 12 MONTHS</text>',
        f'<text x="{width-26}" y="33" text-anchor="end" fill="{MUTED}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="9" letter-spacing="1">PUBLIC + PRIVATE TOTALS</text>',
        f'<line x1="26" y1="48" x2="{width-26}" y2="48" stroke="{BORDER}"/>',
    ]

    month_seen: set[tuple[int, int]] = set()
    cursor = start
    while cursor <= end:
        key = (cursor.year, cursor.month)
        if cursor.day == 1 and key not in month_seen:
            month_seen.add(key)
            column = (cursor - grid_start).days // 7
            x = grid_x + column * pitch
            parts.append(
                f'<text x="{x}" y="70" fill="{MUTED}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="9" letter-spacing="1">{escape(cursor.strftime("%b").lower())}</text>'
            )
        cursor += timedelta(days=1)

    for label, row in (("mon", 0), ("wed", 2), ("fri", 4)):
        y = grid_y + row * pitch + 9
        parts.append(
            f'<text x="26" y="{y}" fill="{MUTED}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="9">{label}</text>'
        )

    offset = 0
    total_days = (grid_end - grid_start).days + 1
    while offset < total_days:
        day = grid_start + timedelta(days=offset)
        column, row = offset // 7, day.weekday()
        x, y = grid_x + column * pitch, grid_y + row * pitch
        if day < start or day > end:
            fill = "#111820"
            shown_count = 0
        else:
            shown_count = days.get(day, 0)
            fill = LEVEL_COLORS[contribution_level(shown_count, positives)]
        tooltip = f"{day.isoformat()}: {shown_count} contributions"
        parts.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" fill="{fill}"><title>{escape(tooltip)}</title></rect>'
        )
        offset += 1

    metric_x = [26, 270, 514, 758]
    metric_items = [
        (f'{metrics["total"]:,}', "CONTRIBUTIONS", "public + private"),
        (f'{metrics["current_streak"]}d', "CURRENT STREAK", "consecutive days"),
        (f'{metrics["longest_streak"]}d', "LONGEST STREAK", "consecutive days"),
        (str(metrics["busiest_count"]), "BUSIEST DAY", metrics["busiest_date"].isoformat() if metrics["busiest_date"] else "no activity yet"),
    ]
    value_colors = [ACCENT, ACCENT_BRIGHT, ACCENT, ACCENT_BRIGHT]
    for i, ((value, label, note), x) in enumerate(zip(metric_items, metric_x)):
        parts.append(
            f'<text x="{x}" y="222" fill="{value_colors[i]}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="23" font-weight="700">{escape(value)}</text>'
        )
        parts.append(
            f'<text x="{x}" y="242" fill="{TEXT}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="9" font-weight="700" letter-spacing="1">{label}</text>'
        )
        parts.append(
            f'<text x="{x}" y="258" fill="{MUTED}" font-family="ui-monospace, SFMono-Regular, Consolas, monospace" font-size="9">{escape(note)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def build_sample_data(end: date) -> dict[date, int]:
    start = end - timedelta(days=364)
    result: dict[date, int] = {}
    for offset in range(365):
        day = start + timedelta(days=offset)
        value = 0
        if day.weekday() not in (5, 6):
            seed = (offset * 17 + day.month * 11) % 13
            if seed > 2:
                value = (seed % 5) + (2 if day.weekday() in (1, 2, 3) else 0)
        if offset in (42, 178, 289):
            value = 14
        result[day] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="assets/activity.svg", help="Output SVG path")
    parser.add_argument("--sample", action="store_true", help="Generate preview SVG using synthetic data")
    args = parser.parse_args()

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=364)
    if args.sample:
        days = build_sample_data(end)
    else:
        token = os.environ.get("GH_CONTRIBUTIONS_TOKEN", "").strip()
        if not token:
            print("Missing GH_CONTRIBUTIONS_TOKEN environment variable.", file=sys.stderr)
            return 2
        try:
            collection = fetch_contributions(token, start, end)
            days = normalize_days(collection, start, end)
            if not collection.get("hasAnyRestrictedContributions"):
                print(
                    "Warning: no restricted contributions reported. Check the GitHub private-contribution setting and the token's read:user scope.",
                    file=sys.stderr,
                )
        except (RuntimeError, KeyError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 1

    metrics = calculate_metrics(days, end)
    svg = render_svg(days, start, end, metrics)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    print(
        f"Updated {output}: {metrics['total']:,} contributions, current streak {metrics['current_streak']}d, "
        f"longest streak {metrics['longest_streak']}d, busiest day {metrics['busiest_count']} ({metrics['busiest_date']})."
    )
    if args.sample:
        print("Sample preview only: all displayed contribution values are synthetic.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
