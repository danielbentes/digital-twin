#!/usr/bin/env python3
"""
quantitative.py — Phase 3a of the digital-twin skill.

Reads corpus.jsonl and computes the headline numbers that anchor every other
analysis pass:
  * total prompt count
  * average + median + p90 prompt length
  * slash-command frequency table
  * vocabulary frequencies (top 100 unigrams, top 50 bigrams, after stopword
    removal)
  * top-N first words (verbs that start prompts: "investigate", "fix", "ship",
    "review", ...)
  * steering verbs (top approval words: "proceed", "continue", "yes", "go", and
    top pushback words: "stop", "wait", "no", "don't")
  * language-marker detection: auto-detect dominant non-English language by
    counting language-specific stopwords + character markers
  * per-project prompt share

Outputs:
  numbers.json      — machine-readable counts
  numbers.md        — human-readable canonical numbers (template-fillable)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Stopwords — kept minimal. Covers common English + Norwegian + German + Spanish
# + French function words so they don't dominate the unigram count.
STOPWORDS = {
    # English
    "the", "a", "an", "is", "it", "and", "or", "but", "of", "to", "in",
    "on", "at", "for", "with", "as", "by", "from", "this", "that", "these",
    "those", "i", "you", "he", "she", "we", "they", "be", "are", "was",
    "were", "been", "being", "have", "has", "had", "do", "does", "did",
    "if", "then", "than", "so", "not", "no", "yes", "can", "could", "would",
    "should", "will", "shall", "may", "might", "must", "let", "lets", "me",
    "my", "your", "our", "their", "his", "her", "its", "any", "all", "some",
    "what", "when", "where", "why", "how", "which", "who", "whom", "there",
    "here", "now", "also", "just", "only", "too", "very", "much", "many",
    # Norwegian
    "og", "i", "jeg", "det", "at", "en", "et", "den", "til", "er", "som",
    "på", "de", "med", "han", "av", "ikke", "ikkje", "der", "så", "var",
    "meg", "seg", "men", "ett", "har", "om", "vi", "min", "mitt", "mine",
    "deg", "kan", "kunne", "skulle", "ville", "blir", "ble", "være", "bli",
    "ha", "være",
    # German
    "und", "der", "die", "das", "den", "dem", "ein", "eine", "einer", "ich",
    "du", "er", "sie", "es", "wir", "ihr", "ist", "sind", "war", "waren",
    "haben", "hat", "habe", "auf", "aus", "bei", "mit", "nach", "von", "zu",
    "für", "über", "unter", "wenn", "dann", "aber", "oder", "nicht", "kein",
    # Spanish
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "pero",
    "que", "porque", "como", "cuando", "donde", "si", "no", "ser", "estar",
    "tener", "hacer", "ir", "me", "te", "se", "nos", "os", "lo", "le",
    # French
    "le", "la", "les", "un", "une", "des", "et", "ou", "mais", "donc", "or",
    "ni", "car", "que", "qui", "ce", "cet", "cette", "ces", "mon", "ton",
    "son", "notre", "votre", "leur", "je", "tu", "il", "elle", "nous", "vous",
    "ils", "elles", "est", "sont", "était", "étaient",
}

# Language marker patterns — used to detect dominant non-English language.
# A prompt counts toward language X if ANY of its markers appear.
LANGUAGE_MARKERS = {
    "norwegian": re.compile(r"\b(?:jeg|ikke|ikkje|også|på|hvor|nå|fordi|skal|kanskje|hvorfor|hva)\b", re.IGNORECASE),
    "german": re.compile(r"\b(?:nicht|auch|aber|sind|wäre|würde|möchte|über|für|nach|gegen)\b", re.IGNORECASE),
    "spanish": re.compile(r"\b(?:porque|también|cuando|donde|hacer|tener|estar|pero|hola|gracias)\b", re.IGNORECASE),
    "french": re.compile(r"\b(?:pourquoi|aussi|mais|sont|peut|faire|avoir|être|merci|bonjour)\b", re.IGNORECASE),
    "portuguese": re.compile(r"\b(?:obrigado|também|porque|quando|onde|fazer|ter|estar|mas|olá)\b", re.IGNORECASE),
}

# Approval / pushback verb sets — these are the conversational steering words.
APPROVAL_WORDS = {
    "proceed", "continue", "yes", "go", "ok", "okay", "sounds", "great",
    "perfect", "ship", "merge", "do", "👍",
}
PUSHBACK_WORDS = {
    "stop", "wait", "no", "don't", "dont", "actually", "but", "however",
    "hold", "pause", "revert", "rollback",
}

TOKEN_RE = re.compile(r"\b[\w'-]{2,}\b", re.UNICODE)
SLASH_RE = re.compile(r"(?:^|[\s`])(/[a-z][a-z0-9_:-]*)", re.IGNORECASE)
SLASH_WHITELIST = {
    "/agents",
    "/clear",
    "/compact",
    "/cost",
    "/doctor",
    "/flow",
    "/frontend-design",
    "/help",
    "/init",
    "/memory",
    "/model",
    "/permissions",
    "/plugin",
    "/plugins",
    "/review",
    "/ship",
    "/skills",
    "/status",
}


def is_probable_slash_command(cmd: str) -> bool:
    """Filter path/API fragments out of slash-command metrics."""
    if ":" in cmd:
        return True
    return cmd in SLASH_WHITELIST


def tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text)]


def first_word(text: str) -> str | None:
    # Skip leading slash commands and common formatting noise.
    stripped = text.lstrip().lstrip("/-#*>").strip()
    if not stripped:
        return None
    m = TOKEN_RE.match(stripped)
    return m.group(0).lower() if m else None


def percentile(values: list[int], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = (len(s) - 1) * q
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return s[f] + (s[c] - s[f]) * (k - f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus",
        default=os.path.expanduser("~/.claude/digital-twin/corpora/corpus.jsonl"),
    )
    ap.add_argument(
        "--out-json",
        default=os.path.expanduser("~/.claude/digital-twin/analysis/numbers.json"),
    )
    ap.add_argument(
        "--out-md",
        default=os.path.expanduser("~/.claude/digital-twin/analysis/numbers.md"),
    )
    ap.add_argument("--top-unigrams", type=int, default=100)
    ap.add_argument("--top-bigrams", type=int, default=50)
    ap.add_argument("--top-first-words", type=int, default=30)
    args = ap.parse_args()

    corpus_path = Path(args.corpus).expanduser()
    if not corpus_path.exists():
        print(f"ERROR: corpus not found: {corpus_path}", file=sys.stderr)
        print("Run extract-corpus.py first.", file=sys.stderr)
        return 2

    out_json = Path(args.out_json).expanduser()
    out_md = Path(args.out_md).expanduser()
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    prompts_with_slash = 0
    lengths: list[int] = []
    slash_counter: Counter[str] = Counter()
    unigrams: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    first_words: Counter[str] = Counter()
    approvals = 0
    pushbacks = 0
    approval_word_counter: Counter[str] = Counter()
    pushback_word_counter: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    per_project: Counter[str] = Counter()
    per_project_human: Counter[str] = Counter()
    source_type_counts: Counter[str] = Counter()
    human_typed_count = 0

    with open(corpus_path, encoding="utf-8") as fp:
        for line in fp:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = rec.get("text", "")
            if not text:
                continue

            n += 1
            lengths.append(len(text))
            is_human = bool(rec.get("is_human_typed", True))
            source_type_counts[
                rec.get("source_type") or rec.get("type") or "unknown"
            ] += 1
            per_project[rec.get("project", "unknown")] += 1
            if is_human:
                human_typed_count += 1
                per_project_human[rec.get("project", "unknown")] += 1

            prompt_has_slash = False
            if is_human:
                for m in SLASH_RE.finditer(text):
                    cmd = m.group(1).lower()
                    if not is_probable_slash_command(cmd):
                        continue
                    slash_counter[cmd] += 1
                    prompt_has_slash = True
            if is_human and prompt_has_slash:
                prompts_with_slash += 1

            if is_human:
                toks = tokenize(text)
                kept = [t for t in toks if t not in STOPWORDS]
                unigrams.update(kept)
                for i in range(len(kept) - 1):
                    bigrams[f"{kept[i]} {kept[i + 1]}"] += 1

            if is_human:
                fw = first_word(text)
                if fw:
                    first_words[fw] += 1
                    if fw in APPROVAL_WORDS:
                        approvals += 1
                        approval_word_counter[fw] += 1
                    if fw in PUSHBACK_WORDS:
                        pushbacks += 1
                        pushback_word_counter[fw] += 1

                for lang, pattern in LANGUAGE_MARKERS.items():
                    if pattern.search(text):
                        language_counts[lang] += 1

    avg_len = round(sum(lengths) / n, 1) if n else 0.0
    median_len = percentile(lengths, 0.5)
    p90_len = percentile(lengths, 0.9)

    total_slashes = sum(slash_counter.values())
    # slash_share = % of prompts that contain at least one slash command,
    # NOT the total-slash-tokens / prompts ratio (which can exceed 100%).
    slash_share = (
        round(100 * prompts_with_slash / human_typed_count, 1)
        if human_typed_count else 0.0
    )

    # Dominant non-English language: highest count, but only if it's at least
    # 5% of all prompts AND beats the next contender by 2x.
    sorted_langs = language_counts.most_common()
    dominant_lang = None
    dominant_share = 0.0
    if sorted_langs:
        top_lang, top_count = sorted_langs[0]
        share = top_count / human_typed_count if human_typed_count else 0.0
        if share >= 0.05:
            if len(sorted_langs) == 1 or top_count >= 2 * sorted_langs[1][1]:
                dominant_lang = top_lang
                dominant_share = round(100 * share, 1)

    numbers = {
        "n_prompts": n,
        "n_prompts_human_typed": human_typed_count,
        "n_prompts_by_source_type": dict(source_type_counts),
        "avg_prompt_length_chars": avg_len,
        "median_prompt_length_chars": median_len,
        "p90_prompt_length_chars": p90_len,
        "total_slash_invocations": total_slashes,
        "n_prompts_with_slash": prompts_with_slash,
        "slash_share_pct": slash_share,
        "top_slash_commands": slash_counter.most_common(20),
        "top_unigrams": unigrams.most_common(args.top_unigrams),
        "top_bigrams": bigrams.most_common(args.top_bigrams),
        "top_first_words": first_words.most_common(args.top_first_words),
        "approval_count": approvals,
        "pushback_count": pushbacks,
        "top_approval_words": approval_word_counter.most_common(),
        "top_pushback_words": pushback_word_counter.most_common(),
        "dominant_second_language": dominant_lang,
        "dominant_second_language_share_pct": dominant_share,
        "language_marker_counts": dict(sorted_langs),
        "per_project_top20": per_project.most_common(20),
        "per_project_human_top20": per_project_human.most_common(20),
        "n_projects": len(per_project),
    }

    with open(out_json, "w", encoding="utf-8") as fp:
        json.dump(numbers, fp, indent=2, ensure_ascii=False)

    # Markdown rendering
    md = []
    md.append("# Canonical Numbers (auto-generated by digital-twin)\n")
    md.append(f"- **Total prompts:** {n:,}")
    md.append(f"- **Human-typed prompts:** {human_typed_count:,}")
    md.append(f"- **Projects with prompts:** {len(per_project)}")
    md.append(f"- **Average prompt length:** {avg_len} chars (median {median_len:.0f}, p90 {p90_len:.0f})")
    md.append(f"- **Slash-command invocations:** {total_slashes:,} ({slash_share}% of human-typed prompts)")
    md.append(f"- **Approvals (first-word match):** {approvals:,}")
    md.append(f"- **Pushbacks (first-word match):** {pushbacks:,}")
    if dominant_lang:
        md.append(f"- **Dominant non-English language:** {dominant_lang} ({dominant_share}% of prompts)")
    else:
        md.append("- **Dominant non-English language:** none detected above the 5% threshold")
    md.append("")

    md.append("## Top slash commands\n")
    md.append("| Command | Count |")
    md.append("| --- | ---: |")
    for cmd, c in slash_counter.most_common(20):
        md.append(f"| `{cmd}` | {c:,} |")
    md.append("")

    md.append("## Top first words (steering verbs)\n")
    md.append("| Word | Count |")
    md.append("| --- | ---: |")
    for w, c in first_words.most_common(args.top_first_words):
        md.append(f"| {w} | {c:,} |")
    md.append("")

    md.append("## Top approval words\n")
    md.append("| Word | Count |")
    md.append("| --- | ---: |")
    for w, c in approval_word_counter.most_common():
        md.append(f"| {w} | {c:,} |")
    md.append("")

    md.append("## Top pushback words\n")
    md.append("| Word | Count |")
    md.append("| --- | ---: |")
    for w, c in pushback_word_counter.most_common():
        md.append(f"| {w} | {c:,} |")
    md.append("")

    md.append("## Top unigrams (after stopword filtering)\n")
    md.append("| Token | Count |")
    md.append("| --- | ---: |")
    for w, c in unigrams.most_common(50):
        md.append(f"| {w} | {c:,} |")
    md.append("")

    md.append("## Top bigrams\n")
    md.append("| Bigram | Count |")
    md.append("| --- | ---: |")
    for w, c in bigrams.most_common(30):
        md.append(f"| {w} | {c:,} |")
    md.append("")

    md.append("## Per-project prompt share (top 20)\n")
    md.append("| Project | Prompts | Share |")
    md.append("| --- | ---: | ---: |")
    for proj, c in per_project.most_common(20):
        share = round(100 * c / n, 1) if n else 0.0
        md.append(f"| {proj} | {c:,} | {share}% |")
    md.append("")

    with open(out_md, "w", encoding="utf-8") as fp:
        fp.write("\n".join(md))

    print(f"Wrote: {out_json}")
    print(f"Wrote: {out_md}")
    print(f"\nQuick summary:")
    print(f"  n_prompts: {n:,}")
    print(f"  human:    {human_typed_count:,}")
    print(f"  avg_len:   {avg_len} chars")
    print(f"  slash:     {total_slashes:,} ({slash_share}%)")
    print(f"  approvals: {approvals:,}   pushbacks: {pushbacks:,}")
    if dominant_lang:
        print(f"  language:  {dominant_lang} ({dominant_share}%)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
