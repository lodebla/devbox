# OMP Devbox for ZimaOS

Persistent coding workstation designed for a ZimaOS server:

- SSH + tmux
- Oh My Pi (OMP)
- `orca-cli/orca`
- `rg`, Git, `gh`, Git LFS
- Vim + latest stable Neovim with persistent Kickstart.nvim configuration
- Bun, Node/npm, Python, Go, build tools
- persistent Chromium on Xvfb
- OMP connected to the shared Chromium through Chrome DevTools MCP
- optional noVNC GUI (`browser-gui start` / `stop`)
- sanitized local → server OMP config sync
- helper commands for persistent OMP/tmux sessions
- Fusion Harness multi-model orchestration integrated with OMP
- automatic Command Code provider and stack seeding
- deterministic Fusion Harness compatibility tests

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
vim README.md
nvim README.md
omp-session start myproject /workspace/myproject
omp-session attach myproject
omp-session capture myproject 200
omp-session send myproject "run the tests"
```

## Fusion Harness in OMP

The image ships the OMP-compatible Fusion Harness extension at
`/opt/omp/fusion-harness/fusion-harness.ts`, installs the
`pi-commandcode-provider` plugin, and seeds the persistent default stack at
`~/.omp/agent/fusion-harness/model-stack-trio.yaml` on first boot. Existing
OMP extensions and an existing stack are preserved. After `sync-omp-import`,
the container-local extension path is restored automatically.

Inside `omp`:

```text
/fh
/fh on
/fh-system-prompt
/fh-only <slot> <prompt>
/fh-opinion <prompt>
/fh-fusion "<research prompt>" "<merge instruction>"
/fh-debate [--rounds N] <prompt>
/fh-collaborate <prompt>
/fh-model
/fh-reset
```

Edit the persistent stack after checking the models available to the
authenticated OMP account:

```bash
omp models --json
$EDITOR ~/.omp/agent/fusion-harness/model-stack-trio.yaml
```

See [`docs/fusion-harness-omp.md`](docs/fusion-harness-omp.md) for the
provider, authentication, child-compatibility, and smoke-test details.

## Vim / Neovim

The image includes full `vim` plus the latest stable Neovim from the official release tarball. Kickstart.nvim is seeded from `nvim-lua/kickstart.nvim` at image build time.

On first container start, Kickstart is copied to `/persist/nvim` and exposed to Neovim as `/persist/config/nvim` (the container uses `XDG_CONFIG_HOME=/persist/config`). Existing Neovim configuration is never overwritten. Plugin/data state lives under the already-persistent XDG data directory.

Useful checks:

```bash
vim --version | head -n 1
nvim --version | head -n 1
readlink /persist/config/nvim
```

Kickstart installs its configured plugins on first `nvim` launch.

## OMP configuration sync

Linux/macOS/WSL:

```bash
./sync/sync-omp.sh devbox
```

PowerShell:

```powershell
.\sync\sync-omp.ps1 -Remote devbox
```

The sync intentionally excludes authentication DBs, session history, secrets and local `node_modules`. After the import it automatically runs `bun install` in `~/.omp/plugins` when a plugin `package.json` is present, so Linux plugin dependencies are rehydrated on the devbox. See `GUIDA-ZIMAOS.md` for details.

## Installation

Follow **[GUIDA-ZIMAOS.md](GUIDA-ZIMAOS.md)**. It includes image publishing, ZimaOS Custom App import, SSH, browser GUI, OMP sync and Hermes integration.
