# OMP Devbox for ZimaOS

Persistent coding workstation designed for a ZimaOS server:

- SSH + tmux
- tmux mouse scrolling + true-color defaults for mobile terminals (Termius)
- Tern remote daemon with SSH-key authentication over QUIC (UDP 8376)
- Oh My Pi (OMP)
- OpenAI Codex CLI with persistent `~/.codex` auth/config
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
   +-- Tern :8376/UDP ----> persistent Tern sessions / OMP
   |
   |                              |
   |                              | Chrome DevTools MCP
   |                              v
   |                         Chromium :9222
   |                         (loopback only)
   |                              |
   +-- noVNC :6080 --------------+   [viewer only when enabled]
   |
   +-- panel :7690 ---------> tmux sessions / slash commands / Collab links
   +-- my.omp.sh (Collab, E2E encrypted) <-> OMP sessions

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
omp-session qr myproject      # phone join QR (Collab, full control)
omp-qr                        # list every shared OMP session / show its QR
omp-panel login               # phone panel login QR (sessions, slash commands, keys)
```

## Tern remoto

Il demone di [Tern di Stencil](https://stencil.so/tern) parte automaticamente
come utente `dev` e accetta le chiavi già presenti in
`/persist/ssh/authorized_keys`. Configurazione, sessioni e identità del server
restano in `/persist/tern`; il log del servizio è
`/persist/tern/remote.log`.

Entrambi i Compose pubblicano **8376/UDP**, non TCP. Nell'app Tern aggiungi
`dev@IP_DEL_SERVER:8376`; carica la chiave SSH del devbox nel tuo `ssh-agent`.
Confronta la fingerprint proposta con quella restituita nel container da:

```bash
tern remote host-key --state-dir /persist/tern/remote
```

La build richiede un archivio Linux ufficiale della beta
([download autenticato](https://build.stencil.so/tern)), della versione indicata
da `TERN_VERSION` nel Dockerfile (attualmente `0.9.5`):

```bash
docker build --secret id=tern_amd64,src=./tern-amd64.tar.gz -t omp-devbox:local .
# Oppure, su AMD64:
TERN_ARCHIVE=./tern-amd64.tar.gz docker compose -f docker-compose.local.yml up -d --build
# Su ARM64:
TERN_ARCH=arm64 TERN_ARCHIVE=./tern-arm64.tar.gz docker compose -f docker-compose.local.yml up -d --build
```

Gli archivi non vanno committati. La CI legge gli URL degli archivi forniti dai
segreti `TERN_AMD64_ARCHIVE_URL` e `TERN_ARM64_ARCHIVE_URL` e li passa a BuildKit
come file segreti; nessuna credenziale Stencil entra nell'immagine.
Vedi [la guida](GUIDA-ZIMAOS.md#2-pubblica-una-volta-limmagine-docker) per la
preparazione degli archivi e della CI.

Per collegamenti diretti, consenti UDP 8376 anche nel firewall del server e,
se necessario, nel router. I tunnel SSH e HTTP/Cloudflare non trasportano questo
collegamento QUIC: usa una rotta UDP raggiungibile, ad esempio LAN o VPN.


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


## OMP e Codex aggiornabili

`/opt/omp` e il prefix npm globale `/opt/npm-global` sono assegnati all'utente `dev`, quindi gli updater lanciati dalla sessione normale non falliscono con `EACCES`. Codex è installato nell'immagine come `@openai/codex`; il suo stato/login vive in `/persist/codex` tramite `~/.codex`, quindi sopravvive alle ricreazioni del container.

Per il login Codex puoi usare:

```bash
codex login --device-auth
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

The sync intentionally excludes authentication DBs, session history, secrets and local `node_modules`. After the import it automatically runs `bun install` in `~/.omp/plugins` when a plugin `package.json` is present, so Linux plugin dependencies are rehydrated on the devbox. See `GUIDA-ZIMAOS.md` for details.

## Installation

Follow **[GUIDA-ZIMAOS.md](GUIDA-ZIMAOS.md)**. It includes image publishing, ZimaOS Custom App import, SSH, browser GUI, OMP sync and Hermes integration.

### SSH keys persistenti

`DEVBOX_AUTHORIZED_KEYS` viene usata come chiave bootstrap: all'avvio viene aggiunta a `/persist/ssh/authorized_keys` solo se manca. Il file non viene più sovrascritto, quindi eventuali chiavi aggiunte manualmente (per esempio Termius) restano presenti dopo restart o ricreazioni del container, purché `/persist` sia montato sul volume persistente.
