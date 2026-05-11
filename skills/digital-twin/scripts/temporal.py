#!/usr/bin/env python3
"""
temporal.py — Phase 3b of the digital-twin skill.

Reads timestamped.jsonl and computes:
  * hour-of-day histogram (local time zone of the user's machine)
  * day-of-week histogram
  * work-burst detection (gaps >2 hours split sessions; report burst lengths)
  * recovery cycle distribution (length in turns from a pushback prompt back
    to a "proceed"-class approval)
  * vocabulary drift over time (compare first 25% of corpus vs last 25%)

Outputs:
  temporal.json — machine-readable
  temporal.md   — human-readable with ASCII charts
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

APPROVAL_WORDS = {
    "proceed", "continue", "yes", "go", "ok", "okay", "sounds", "great",
    "perfect", "ship", "merge",
}
PUSHBACK_WORDS = {
    "stop", "wait", "no", "don't", "dont", "actually", "but", "however",
    "hold", "pause", "revert", "rollback",
}

TOKEN_RE = re.compile(r"\b[\w'-]{2,}\b", re.UNICODE)


def first_word(text: str) -> str | None:
    stripped = text.lstrip().lstrip("/-#*>").strip()
    if not stripped:
        return None
    m = TOKEN_RE.match(stripped)
    return m.group(0).lower() if m else None


def parse_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        # ISO 8601 with optional Z
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


def ascii_bar(value: int, max_value: int, width: int = 40) -> str:
    if max_value <= 0:
        return ""
    return "█" * int(round(width * value / max_value))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--timestamped",
        default=os.path.expanduser(
            "~/.claude/digital-twin/corpora/timestamped.jsonl"
        ),
    )
    ap.add_argument(
        "--out-json",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/temporal.json"
        ),
    )
    ap.add_argument(
        "--out-md",
        default=os.path.expanduser(
            "~/.claude/digital-twin/analysis/temporal.md"
        ),
    )
    ap.add_argument(
        "--gap-minutes",
        type=int,
        default=120,
        help="Minutes between consecutive prompts that splits work bursts.",
    )
    ap.add_argument(
        "--tz-offset-hours",
        type=int,
        default=0,
        help=(
            "Hours offset from UTC for display. Default 0 means UTC. "
            "User may pass their local offset (e.g., +1 for Oslo winter)."
        ),
    )
    args = ap.parse_args()

    ts_path = Path(args.timestamped).expanduser()
    if not ts_path.exists():
        print(f"ERROR: timestamped corpus not found: {ts_path}", file=sys.stderr)
        return 2

    out_json = Path(args.out_json).expanduser()
    out_md = Path(args.out_md).expanduser()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    tz = timezone(timedelta(hours=args.tz_offset_hours))

    records: list[dict] = []
    with open(ts_path, encoding="utf-8") as fp:
        for line in fp:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            dt = parse_ts(rec.get("ts"))
            if not dt:
                continue
            local = dt.astimezone(tz)
            rec["_dt"] = local
            records.append(rec)

    if not records:
        print("ERROR: no parseable timestamps in corpus", file=sys.stderr)
        return 2

    records.sort(key=lambda r: r["_dt"])

    # Hour and day histograms
    hour_hist: Counter[int] = Counter()
    dow_hist: Counter[int] = Counter()
    for rec in records:
        hour_hist[rec["_dt"].hour] += 1
        dow_hist[rec["_dt"].weekday()] += 1  # Monday=0

    # Work bursts: split on gap_minutes
    bursts: list[int] = []
    current = 1
    for i in range(1, len(records)):
        gap = (records[i]["_dt"] - records[i - 1]["_dt"]).total_seconds() / 60
        if gap > args.gap_minutes:
            bursts.append(current)
            current = 1
        else:
            current += 1
    bursts.append(current)

    # Recovery cycles: walk per-session, find pushback→approval gaps in turns
    by_session: dict[str, list[dict]] = defaultdict(list)
    for rec in records:
        by_session[rec.get("session", "?")].append(rec)

    recovery_cycles: list[int] = []
    for session, prompts in by_session.items():
        prompts.sort(key=lambda r: r["_dt"])
        in_recovery = False
        recovery_start = 0
        for i, rec in enumerate(prompts):
            fw = first_word(rec.get("text", ""))
            if fw is None:
                continue
            if not in_recovery and fw in PUSHBACK_WORDS:
                in_recovery = True
                recovery_start = i
            elif in_recovery and fw in APPROVAL_WORDS:
                recovery_cycles.append(i - recovery_start)
                in_recovery = False

    recovery_stats = {
        "n_recovery_cycles": len(recovery_cycles),
        "median_turns": percentile(recovery_cycles, 0.5),
        "p75_turns": percentile(recovery_cycles, 0.75),
        "p90_turns": percentile(recovery_cycles, 0.90),
        "max_turns": max(recovery_cycles) if recovery_cycles else 0,
    }

    # Vocabulary drift: first 25% vs last 25%
    quartile = max(1, len(records) // 4)
    early = records[:quartile]
    late = records[-quartile:]

    def vocab_top(recs: list[dict], k: int = 25) -> list[tuple[str, int]]:
        c: Counter[str] = Counter()
        for r in recs:
            for tok in TOKEN_RE.findall(r.get("text", "").lower()):
                if len(tok) >= 4:
                    c[tok] += 1
        return c.most_common(k)

    early_vocab = vocab_top(early)
    late_vocab = vocab_top(late)
    early_set = {w for w, _ in early_vocab}
    late_set = {w for w, _ in late_vocab}
    rising = sorted(late_set - early_set)
    falling = sorted(early_set - late_set)

    # Find peak hour & peak day
    peak_hour = hour_hist.most_common(1)[0] if hour_hist else (None, 0)
    peak_day = dow_hist.most_common(1)[0] if dow_hist else (None, 0)
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    summary = {
        "n_timestamped_prompts": len(records),
        "date_range": {
            "start": records[0]["_dt"].isoformat(),
            "end": records[-1]["_dt"].isoformat(),
        },
        "tz_offset_hours": args.tz_offset_hours,
        "hour_histogram": dict(sorted(hour_hist.items())),
        "dow_histogram": {
            dow_names[k]: v for k, v in sorted(dow_hist.items())
        },
        "peak_hour": peak_hour[0],
        "peak_hour_count": peak_hour[1],
        "peak_day": dow_names[peak_day[0]] if peak_day[0] is not None else None,
        "peak_day_count": peak_day[1],
        "work_bursts": {
            "n_bursts": len(bursts),
            "median_burst_size": percentile([float(b) for b in bursts], 0.5),
            "p90_burst_size": percentile([float(b) for b in bursts], 0.9),
            "max_burst_size": max(bursts) if bursts else 0,
        },
        "recovery_cycles": recovery_stats,
        "vocab_drift": {
            "early_top": early_vocab,
            "late_top": late_vocab,
            "rising_in_late": rising,
            "fell_off_in_late": falling,
        },
    }

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(summary, fp, indent=2, ensure_ascii=False)

    # Markdown rendering with ASCII charts
    md = []
    md.append("# Temporal Analysis (auto-generated)\n")
    md.append(f"- **Timestamped prompts:** {len(records):,}")
    md.append(
        f"- **Date range:** {records[0]['_dt'].date()} → {records[-1]['_dt'].date()}"
    )
    md.append(f"- **Timezone offset:** UTC{args.tz_offset_hours:+d}")
    md.append(
        f"- **Peak hour:** {peak_hour[0]}:00 ({peak_hour[1]:,} prompts)"
    )
    md.append(
        f"- **Peak day:** {dow_names[peak_day[0]] if peak_day[0] is not None else '?'} ({peak_day[1]:,} prompts)"
    )
    md.append("")

    md.append("## Hour of day\n")
    max_hour = max(hour_hist.values()) if hour_hist else 1
    for h in range(24):
        v = hour_hist.get(h, 0)
        md.append(f"{h:02d}:00 | {ascii_bar(v, max_hour)} {v:,}")
    md.append("")

    md.append("## Day of week\n")
    max_dow = max(dow_hist.values()) if dow_hist else 1
    for i, name in enumerate(dow_names):
        v = dow_hist.get(i, 0)
        md.append(f"{name} | {ascii_bar(v, max_dow)} {v:,}")
    md.append("")

    md.append("## Work bursts\n")
    md.append(f"- **N bursts:** {summary['work_bursts']['n_bursts']:,}")
    md.append(
        f"- **Median burst size:** {summary['work_bursts']['median_burst_size']:.1f} prompts"
    )
    md.append(
        f"- **P90 burst size:** {summary['work_bursts']['p90_burst_size']:.1f} prompts"
    )
    md.append(
        f"- **Max burst size:** {summary['work_bursts']['max_burst_size']:,} prompts"
    )
    md.append("")

    md.append("## Recovery cycles (pushback → approval, in turns)\n")
    md.append(f"- **N cycles:** {recovery_stats['n_recovery_cycles']:,}")
    md.append(f"- **Median:** {recovery_stats['median_turns']:.1f}")
    md.append(f"- **P75:** {recovery_stats['p75_turns']:.1f}")
    md.append(f"- **P90:** {recovery_stats['p90_turns']:.1f}")
    md.append(f"- **Max:** {recovery_stats['max_turns']}")
    md.append("")

    md.append("## Vocabulary drift\n")
    md.append("### Rising in late corpus (not in top-25 of early)\n")
    md.append(", ".join(rising) if rising else "_none_")
    md.append("")
    md.append("### Fell off (in top-25 of early, not in late)\n")
    md.append(", ".join(falling) if falling else "_none_")
    md.append("")

    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_md}")
    print(f"\nQuick summary:")
    print(f"  timestamped prompts: {len(records):,}")
    print(f"  peak hour: {peak_hour[0]}:00 ({peak_hour[1]:,})")
    print(
        f"  peak day:  {dow_names[peak_day[0]] if peak_day[0] is not None else '?'} ({peak_day[1]:,})"
    )
    print(
        f"  recovery:  median {recovery_stats['median_turns']:.1f} | p90 {recovery_stats['p90_turns']:.1f} turns"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
