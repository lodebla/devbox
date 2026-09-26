---
name: devbox-sessions
description: Use when the user (often from the phone via Collab) asks to start, list, stop, or get the link of an OMP session on this devbox, or to run a slash command (/model, /compact, /new, …) in another OMP session. Drives tmux sessions with omp-session / omp-qr.
---

# Devbox OMP sessions

OMP sessions on this devbox run in tmux as `omp-<name>` and are shared through
Collab automatically (`collab.autoStart: control`). Collab guests (the phone
browser) can only prompt the agent: they cannot start sessions or run slash
commands. You bridge that gap with deterministic helpers. Never invent links.

## Commands

| Need | Run |
| --- | --- |
| List shared sessions (JSON, no links) | `omp-qr --json` |
| List tmux sessions | `omp-session list` |
| Start a session | `omp-session start <name> <dir>` (name: letters, digits, `.` `_` `-`; create `<dir>` first if missing) |
| Full-control link | `omp-qr --url <name>` |
| Slash command / text in another session | `omp-session send <name> "/compact"` |
| Screen of another session | `omp-session capture <name> 60` |
| Stop a session | `omp-session stop <name>` (confirm with the user first) |

`<name>` is the part after `omp-`. Sessions not started by `omp-session` (e.g.
tmux `box`) are addressed by exact tmux name in `omp-qr`; use
`tmux send-keys -t '=<session>:' -l -- "<text>"` then `tmux send-keys -t '=<session>:' Enter`.

## Reply format

After starting a session or when asked for a link, reply with the link as a
clickable Markdown link on its own line: `[Apri <name>](<url>)`. The phone
opens it directly; do not print QR codes (the user is already on the phone).

## Limits

- Do not send slash commands to **your own** session: they would land while
  you are mid-turn and be queued or lost. Tell the user to use the phone panel
  (`omp-panel`) or Termius for that.
- Interactive selectors (`/model` without arguments, `/resume`, `/tree`) need
  arrow keys: prefer argument forms (`/model <provider/id>`) or point the user
  to the phone panel, which has arrow/Enter/Esc buttons.
- After `/new`, `/resume` or `/fork` the Collab link changes: fetch a fresh one
  with `omp-qr --url <name>`.
