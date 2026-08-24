# OMP Devbox Design

## Goal
Create a persistent Docker-based coding workstation for ZimaOS that remains usable while the user's PCs are off, keeps OMP/tmux state server-side, includes orca-cli and common development tools, and can expose the same Chromium session to OMP, Hermes, and an optional noVNC viewer.

## Architecture
A single `omp-devbox` container runs SSH, tmux, OMP, orca-cli, development tooling, Xvfb/Openbox, and one persistent Chromium instance. Chromium exposes CDP only on container loopback (`127.0.0.1:9222`). The released OMP built-in browser is disabled by a server-only settings overlay; OMP discovers a server-only Chrome DevTools MCP definition that connects to this shared Chromium. The user's synchronized `~/.omp` remains separate from this server-specific browser wiring.

The GUI transport is off by default. `browser-gui start` starts x11vnc + websockify/noVNC against the existing Xvfb display; `browser-gui stop` removes only the viewer, not Chromium. Port 6080 may be published once in ZimaOS, but has no listener while the viewer is stopped.

Hermes can reach the same browser through an SSH local-forward from its own container to devbox's loopback CDP port, then set `browser.cdp_url` (or `BROWSER_CDP_URL`) to that local tunnel endpoint. CDP is never published by Docker.

## Persistence
Use two host mounts:
- `/persist`: OMP state/config, SSH authorized keys, Orca state, XDG config, Chromium profile.
- `/workspace`: repositories and worktrees.

The image installs binaries outside `/home/dev`, so persistent mounts cannot hide OMP/Bun binaries after a container recreate.

## OMP Sync
Provide Linux/macOS/WSL and PowerShell client scripts that create a sanitized archive of local `~/.omp` and import it over SSH. Default exclusions protect machine-local/runtime-sensitive files (`agent.db`, `.env`, sessions/blobs/logs, auth tokens, `node_modules`). Marketplace/plugin source and manifests are synchronized; server-side `bun install` restores platform-specific npm dependencies. The server-specific settings overlay and Chrome DevTools MCP definition live outside `~/.omp`, so sync cannot overwrite them.

## Security
- SSH password login disabled; public-key auth only.
- Root SSH login disabled.
- CDP bound to loopback only.
- noVNC requires a VNC password before it can start.
- noVNC is designed for LAN/SSH tunnel/Cloudflare Access; do not expose unauthenticated 6080 directly to the Internet.
- Dev user has passwordless sudo inside the container for practical development tooling; this grants root only inside this container but still allows modification of mounted data.

## ZimaOS Workflow
The source bundle includes a Dockerfile and a ZimaOS-oriented compose file. Since ZimaOS custom-app import pulls an image rather than receiving the Dockerfile from ChatGPT, the guide includes a one-time image build/push step (local registry/GHCR/Docker Hub) and then UI-only ZimaOS import. Daily management happens through SSH commands inside the container.
