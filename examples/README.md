# Examples

Anonymized sample outputs and configuration snippets.

- `sample-PROFILE.md` — A sample profile generated from a 300-prompt synthetic corpus. Shows the structure, narrative sections, and ASCII charts.
- `sample-PROFILE.html` — Same content with inline SVG charts. Open in any browser to preview what `/digital-twin:init` produces.
- `sample-CLAUDE-md-patch.md` — Sample CLAUDE.md patch suggesting global defaults.
- `hook-config.json` — Sample `PostToolUse` hook config for the pushback detector. Not auto-installed.

These samples come from `tests/conftest.py`'s synthetic-corpus fixture and contain no real user data. They illustrate the output shape; a real `/digital-twin:init` run against 5k-20k prompts produces much richer narrative sections.

To generate your own profile, install the plugin and run `/digital-twin:init`.
