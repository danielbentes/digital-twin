import json
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PLUGIN_ROOT / "skills" / "digital-twin" / "scripts"


def _run(*args):
    result = subprocess.run(args, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return result


def test_extract_prefers_full_user_over_last_prompt(tmp_path: Path):
    source = tmp_path / "projects"
    session_dir = source / "-tmp-proj"
    session_dir.mkdir(parents=True)
    session = session_dir / "s.jsonl"
    full_prompt = (
        "full user prompt with enough detail to prefer this over the cache row "
        "and preserve the complete wording for style extraction"
    )
    rows = [
        {"type": "last-prompt", "lastPrompt": full_prompt[:72], "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "user", "timestamp": "2026-01-01T00:00:01Z", "message": {"role": "user", "content": full_prompt}},
    ]
    session.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "out"

    _run(
        sys.executable,
        str(SCRIPTS / "extract-corpus.py"),
        "--source",
        str(source),
        "--out",
        str(out),
    )
    corpus = [json.loads(line) for line in (out / "corpus.jsonl").read_text().splitlines()]
    assert len(corpus) == 1
    assert corpus[0]["source_type"] == "user"
    assert corpus[0]["is_human_typed"] is True
    assert "full user prompt" in corpus[0]["text"]


def test_extract_keeps_unmatched_last_prompt_in_mixed_session(tmp_path: Path):
    source = tmp_path / "projects"
    session_dir = source / "-tmp-proj"
    session_dir.mkdir(parents=True)
    session = session_dir / "s.jsonl"
    rows = [
        {"type": "last-prompt", "lastPrompt": "ship the already finished PR after checking CI", "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "user", "timestamp": "2026-01-01T00:01:00Z", "message": {"role": "user", "content": "now review the next issue and make a plan"}},
    ]
    session.write_text("\n".join(json.dumps(r) for r in rows))
    out = tmp_path / "out"

    _run(
        sys.executable,
        str(SCRIPTS / "extract-corpus.py"),
        "--source",
        str(source),
        "--out",
        str(out),
    )
    corpus = [json.loads(line) for line in (out / "corpus.jsonl").read_text().splitlines()]
    assert len(corpus) == 2
    assert [row["source_type"] for row in corpus] == ["last-prompt", "user"]
    assert "ship the already finished PR" in corpus[0]["text"]


def test_extract_skips_symlinked_session_files(tmp_path: Path):
    source = tmp_path / "projects"
    session_dir = source / "-tmp-proj"
    session_dir.mkdir(parents=True)
    normal = session_dir / "normal.jsonl"
    normal.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-01-01T00:01:00Z",
        "message": {"role": "user", "content": "normal in-tree prompt"},
    }))

    outside = tmp_path / "outside.jsonl"
    outside.write_text(json.dumps({
        "type": "user",
        "timestamp": "2026-01-01T00:02:00Z",
        "message": {"role": "user", "content": "outside symlink prompt"},
    }))
    try:
        (session_dir / "linked.jsonl").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not allow symlink creation")

    out = tmp_path / "out"
    _run(
        sys.executable,
        str(SCRIPTS / "extract-corpus.py"),
        "--source",
        str(source),
        "--out",
        str(out),
    )
    corpus = [json.loads(line) for line in (out / "corpus.jsonl").read_text().splitlines()]
    assert [row["text"] for row in corpus] == ["normal in-tree prompt"]


def test_memory_inventory_skips_symlinked_memory_files(tmp_path: Path):
    source = tmp_path / "projects"
    memory_dir = source / "-tmp-proj" / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "good.md").write_text(
        "---\nname: Good\ndescription: in tree\ntype: feedback\n---\nSafe body"
    )

    outside = tmp_path / "outside-memory.md"
    outside.write_text(
        "---\nname: Secret\ndescription: outside tree\ntype: feedback\n---\nSecret body"
    )
    try:
        (memory_dir / "linked.md").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("filesystem does not allow symlink creation")

    out_json = tmp_path / "memory.json"
    out_md = tmp_path / "memory.md"
    _run(
        sys.executable,
        str(SCRIPTS / "memory-inventory.py"),
        "--source",
        str(source),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    )
    inventory = json.loads(out_json.read_text())
    assert inventory["n_files"] == 1
    assert inventory["entries"][0]["name"] == "Good"
    assert "Secret body" not in out_md.read_text()


def test_quantitative_filters_path_like_slashes(tmp_path: Path):
    corpus = tmp_path / "corpus.jsonl"
    records = [
        {"project": "p", "text": "Call POST /api/issues and inspect /tmp/output", "is_human_typed": True, "source_type": "user"},
        {"project": "p", "text": "Run /flow:review and then /ship", "is_human_typed": True, "source_type": "user"},
        {"project": "p", "text": "## Paperclip\nPOST /api/issues", "is_human_typed": False, "source_type": "user"},
    ]
    corpus.write_text("\n".join(json.dumps(r) for r in records))
    out_json = tmp_path / "numbers.json"
    out_md = tmp_path / "numbers.md"
    _run(
        sys.executable,
        str(SCRIPTS / "quantitative.py"),
        "--corpus",
        str(corpus),
        "--out-json",
        str(out_json),
        "--out-md",
        str(out_md),
    )
    numbers = json.loads(out_json.read_text())
    commands = dict(numbers["top_slash_commands"])
    assert "/flow:review" in commands
    assert "/ship" in commands
    assert "/api" not in commands
    assert "/tmp" not in commands
    assert numbers["n_prompts_human_typed"] == 2
