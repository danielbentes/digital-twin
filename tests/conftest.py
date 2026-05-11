"""
Shared fixtures for the digital-twin test suite.
"""
import json
import sys
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"
REFERENCES = PLUGIN_ROOT / "skills" / "digital-twin" / "references"

# Make the scripts importable for direct unit tests
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REFERENCES / "visualization"))


APPROVALS = ["proceed", "go", "yes", "ok", "ship", "merge", "great", "perfect"]
PUSHBACKS = ["stop", "wait", "no", "actually", "but", "hold"]
NEUTRAL = ["thanks", "explain", "what", "show", "tell", "how", "where", "when"]


def _make_msg(role: str, text: str, ts: datetime) -> dict:
    return {
        "type": role,
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "message": {"role": role, "content": text},
    }


@pytest.fixture
def synthetic_corpus_dir(tmp_path: Path) -> Path:
    """Create a fake ~/.claude/projects layout with N synthetic sessions."""
    rng = random.Random(42)
    projects_root = tmp_path / "projects"
    projects_root.mkdir()
    # 3 fake projects, ~30 prompts each = 90 prompts total
    base_ts = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
    for proj_i in range(3):
        slug = f"-tmp-test-proj-{proj_i}"
        pdir = projects_root / slug
        pdir.mkdir()
        memdir = pdir / "memory"
        memdir.mkdir()
        # One memory file per project — feedback type
        (memdir / "no_emojis.md").write_text(
            "---\nname: no_emojis\n"
            "description: Do not add emojis to code or commit messages.\n"
            "type: feedback\n---\n\n"
            "Avoid emojis in any synthesized output.\n",
            encoding="utf-8",
        )
        # One session jsonl per project
        sess = pdir / f"session-{proj_i}.jsonl"
        with open(sess, "w", encoding="utf-8") as fp:
            ts = base_ts + timedelta(days=proj_i)
            for turn in range(30):
                ts += timedelta(minutes=rng.randint(1, 10))
                # Assistant turn
                fp.write(json.dumps(_make_msg(
                    "assistant",
                    f"Here's draft {turn}. Proceeding with implementation.",
                    ts,
                )) + "\n")
                # User reply: bias toward approval / occasional pushback
                ts += timedelta(seconds=rng.randint(10, 120))
                r = rng.random()
                if r < 0.5:
                    word = rng.choice(APPROVALS)
                    reply_text = word
                elif r < 0.75:
                    word = rng.choice(PUSHBACKS)
                    reply_text = f"{word} — that's not what I wanted"
                else:
                    word = rng.choice(NEUTRAL)
                    reply_text = f"{word} me how {rng.choice(['this', 'that', 'it'])} works"
                fp.write(json.dumps(_make_msg("user", reply_text, ts)) + "\n")
                # First-prompt only on turn 0
    return projects_root


@pytest.fixture
def synthetic_corpus_jsonl(tmp_path: Path, synthetic_corpus_dir: Path) -> Path:
    """Concatenated corpus.jsonl for downstream pipeline steps."""
    out = tmp_path / "corpus.jsonl"
    with open(out, "w", encoding="utf-8") as fp:
        for sess in sorted(synthetic_corpus_dir.glob("*/*.jsonl")):
            with open(sess, encoding="utf-8") as src:
                fp.write(src.read())
    return out
