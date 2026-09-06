---
name: digital-twin:install-hook
description: Install or uninstall the digital-twin pushback-detector as a Claude Code PostToolUse hook. Explicit, reversible, and incremental — never replays session history.
---

# /digital-twin:install-hook

Install or uninstall the opt-in continuous pushback detector.

The installer is a script, not an in-session action. Run it in your terminal:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/install-hook.py install
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/install-hook.py uninstall
```

Replace `${CLAUDE_PLUGIN_ROOT}` with your plugin directory if invoking outside a Claude Code session (typically `~/.claude/plugins/...` for marketplace installs).

## Check registration status (read-only)

`status` reports whether the hook is registered, without prompting, writing anything, or executing the detector or any hook command:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/install-hook.py status
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/install-hook.py status --settings .claude/settings.json
python3 ${CLAUDE_PLUGIN_ROOT}/skills/digital-twin/scripts/install-hook.py status --settings-file .claude/settings.json
```

It writes exactly one JSON object to standard output and nothing else:

```json
{"version": 1, "installed": false, "managedHookCount": 0}
```

- `version` is the report format version (currently `1`).
- `installed` is `true` when at least one marker-owned digital-twin PostToolUse entry exists in the selected settings file.
- `managedHookCount` is the number of marker-owned entries. Duplicates are counted, not collapsed.
- The object contains no settings values, hook commands, transcript content, or credentials.

Settings selection uses the same `--settings`/`--settings-file` flags and `~/.claude/settings.json` default as `install` and `uninstall`. Missing settings — including a missing parent directory — report `{"version": 1, "installed": false, "managedHookCount": 0}` with exit status `0` and create nothing. Valid settings without a managed marker also report not installed. Malformed JSON, non-object settings, invalid known hook-container or command-field types, and unreadable settings exit nonzero with a clear diagnostic on standard error and no success JSON on standard output.

**Registration is not health.** `"installed": true` means the marker-owned entries exist; it does not mean the detector has executed, is healthy, or will succeed on the next event.

## What `install` does, in order

1. Loads the target settings file and validates its structure. If the JSON is malformed, the installer exits nonzero with a diagnostic and the file is left byte-identical.
2. If a marker-owned digital-twin hook entry already exists, reports "already installed" and does nothing (idempotent).
3. **Prompts for explicit confirmation.** The prompt names the action, shows the canonical settings path, and accepts only `y`/`yes` (case-insensitive). Any other response — including EOF — changes nothing.
4. After confirmation, runs the detector's public `--initialize-offsets` mode: it records each existing session file's last newline-terminated record as the starting offset. **No history is classified and no proposals are created from your past sessions.** If this baseline step fails, settings are unchanged and installation is not completed.
5. Adds exactly one PostToolUse hook entry (matcher `*`) whose command invokes `pushback-detector.py --hook-stdin` with the canonical `--source`, `--state-file`, and `--out-dir`. Marker metadata embedded in the entry records the provenance needed for a reversible uninstall. If the settings file lacked `hooks` or `hooks.PostToolUse`, the marker records that the installer created those containers.

## What `uninstall` does

1. Removes **only** the marker-owned hook entries this installer added.
2. Prunes **only** the containers (`hooks`, `hooks.PostToolUse`) the installer itself created. Your own hooks, and empty containers you authored, are preserved.
3. Requires the same explicit confirmation prompt as `install`.

## Settings, source, state, and queue selection

| Flag | Subcommands | Default |
|---|---|---|
| `--settings` (alias `--settings-file`) | `install`, `uninstall`, `status` | `~/.claude/settings.json` |
| `--source` | `install` | `~/.claude/projects` |
| `--state-file` | `install` | `~/.claude/digital-twin/.state.json` |
| `--out-dir` | `install` | `~/.claude/digital-twin/proposed-rules` |

All paths are canonicalized (realpath) before use, and the same canonical values are embedded in the installed hook command and the marker metadata, so an uninstall is reversible even if you passed non-default paths at install time.

To use a project-local settings file, pass `--settings` to **both** subcommands:

```bash
python3 .../install-hook.py install --settings .claude/settings.json
python3 .../install-hook.py uninstall --settings .claude/settings.json
```

## Hook behavior after installation

- **Event:** Claude Code `PostToolUse`. The PostToolUse hook can run zero, one, or multiple times during an assistant turn, depending on successful matched tool uses. It does not run once per turn, and it does not run on every turn (a turn with no successful tool use triggers no PostToolUse event).
- **Input:** the hook payload arrives on stdin (`--hook-stdin`). The detector processes **only the `transcript_path`** in that payload — there is no fallback to scanning the whole projects root. Other payload fields are ignored.
- **Incremental only:** the detector tracks per-file byte offsets in the state file and reads only new bytes since the last stored offset. Prior sessions are never re-scanned, and the one-time baseline (step 4 above) means your history is never replayed. Manual full scans remain available by running `pushback-detector.py` without `--hook-stdin`, which discovers sessions under `--source` — that is the manual path, never the hook path.
- **Event-local processing:** each hook invocation handles exactly the one transcript named by the event, keeping per-invocation work small.

## Latency

Recurring per-invocation latency is measured separately from the one-time baseline cost of the initial offset initialization. The hook path is filesystem-only and incremental, so its recurring cost scales with new transcript bytes, not corpus size. The one-time baseline scans file boundaries only (no classification) and is paid once, at install.

## Failure visibility

The installed command has **no stdout/stderr redirection and no `|| true` masking**. Detector diagnostics (malformed payloads, state errors, missing transcripts) go to stderr and exit nonzero, so failures are visible rather than silently swallowed. Exit code 2 signals a bad payload or argument; exit code 3 signals detector state errors.

## What the hook never does

- It never writes to memory. It only queues candidate rules under the proposal directory (`--out-dir`).
- Queued proposals enter memory **only** through explicit review and approval via `/digital-twin:propose-rules`. No proposal is ever auto-approved, including by the hook.

## Reviewing the queue

- Run `/digital-twin:status` to see the pending proposal count and queue path.
- Run `/digital-twin:propose-rules` to review, edit, approve, or reject each proposal.
- Or list the files directly: `~/.claude/digital-twin/proposed-rules/*.md`.

## Manual wiring

Prefer the installer. If you must wire the hook by hand, use `examples/hook-config.json` as a sample and match the installer's semantics: matcher `*`, `--hook-stdin`, canonical `--source`/`--state-file`/`--out-dir`, and no output redirection or exit masking.
