# OMP Devbox for ZimaOS

Persistent coding workstation designed for a ZimaOS server:

- SSH + tmux
- Oh My Pi (OMP)
- `orca-cli/orca`
- `rg`, Git, `gh`, Git LFS
- Bun, Node/npm, Python, Go, build tools
- persistent Chromium on Xvfb
- OMP connected to the shared Chromium through Chrome DevTools MCP
- optional noVNC GUI (`browser-gui start` / `stop`)
- sanitized local → server OMP config sync
- helper commands for persistent OMP/tmux sessions

The daily workflow does **not** require Docker or root access on the ZimaOS host after the initial Custom App installation.

## Architecture

```text
PC / phone
   |
   +-- SSH :2222 ---------> tmux / OMP / orca / tools
   |                              |
   |                              | Chrome DevTools MCP
   |                              v
   |                         Chromium :9222
   |                         (loopback only)
   |                              |
   +-- noVNC :6080 --------------+   [viewer only when enabled]

Hermes container
   |
   +-- SSH local forward --------> 127.0.0.1:9222
```

`9222` is intentionally **not published** by Docker.

## Main commands inside devbox

```bash
devbox-health
browser-service status
browser-gui start
browser-gui stop
omp-session start myproject /workspace/myproject
omp-session attach myproject
omp-session capture myproject 200
omp-session send myproject "run the tests"
```

## OMP configuration sync

Linux/macOS/WSL:

```bash
./sync/sync-omp.sh devbox
```

PowerShell:

```powershell
.\sync\sync-omp.ps1 -Remote devbox
```

The sync intentionally excludes authentication DBs, session history, secrets and local `node_modules`. See `GUIDA-ZIMAOS.md` for details.

## Installation

Follow **[GUIDA-ZIMAOS.md](GUIDA-ZIMAOS.md)**. It includes image publishing, ZimaOS Custom App import, SSH, browser GUI, OMP sync and Hermes integration.
