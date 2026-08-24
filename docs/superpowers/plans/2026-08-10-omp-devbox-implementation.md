# OMP Devbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a ZimaOS-friendly persistent coding devbox image with OMP, tmux, orca-cli, shared Chromium, optional noVNC, and safe OMP config synchronization.

**Architecture:** One Debian-based container owns the development workstation and persistent browser. OMP reaches the loopback CDP endpoint through a server-only Chrome DevTools MCP definition while its released built-in browser is disabled to avoid a second browser. GUI viewer processes are controlled at runtime from inside the container and Hermes reaches CDP through SSH forwarding.

**Tech Stack:** Docker, Debian Bookworm, Bash, OpenSSH, tmux, Bun, Node.js, Oh My Pi, Chrome DevTools MCP, Go/orca-cli, Chromium, Xvfb, Openbox, x11vnc, noVNC/websockify, rsync.

## Global Constraints
- Daily operation must not require root access to the ZimaOS host.
- CDP port 9222 must never be published by Docker.
- noVNC must be optional and controlled from inside devbox.
- Local OMP configuration sync must not overwrite server-only browser/MCP wiring.
- Authentication/runtime OMP state must not be synchronized by default.

---

### Task 1: Container image and startup
**Files:** `Dockerfile`, `config/sshd_config`, `bin/entrypoint`
- [ ] Install required development, browser, SSH, VNC, Bun, OMP and orca-cli dependencies.
- [ ] Create non-root `dev` account and server-only OMP settings/MCP wiring.
- [ ] Prepare persistent directory links and authorized_keys on startup.
- [ ] Start browser service and sshd.
- [ ] Verify all shell files with `bash -n`.

### Task 2: Shared browser and optional GUI
**Files:** `bin/browser-service`, `bin/browser-gui`, `config/omp-server.yml`, `config/omp-devbox-mcp.json`
- [ ] Implement idempotent Chromium/Xvfb/Openbox start/status/stop/restart.
- [ ] Bind CDP to loopback only and connect OMP through Chrome DevTools MCP; disable the released built-in browser to avoid a second instance.
- [ ] Implement password-protected x11vnc + noVNC start/status/stop.
- [ ] Verify shell syntax and static security invariants.

### Task 3: OMP configuration synchronization
**Files:** `bin/omp-sync-import`, `sync/sync-omp.sh`, `sync/sync-omp.ps1`
- [ ] Archive local OMP configuration while excluding credentials/runtime/platform node_modules.
- [ ] Transfer over SSH and import with rsync on server.
- [ ] Reinstall Linux-side plugin dependencies where a plugin package manifest exists.
- [ ] Verify exclusion patterns are present in tests.

### Task 4: ZimaOS deployment and operator guide
**Files:** `docker-compose.local.yml`, `zimaos-compose.yml`, `README.md`, `GUIDA-ZIMAOS.md`, `bin/devbox-health`
- [ ] Add local-build compose and registry-image ZimaOS compose.
- [ ] Document one-time build/push and ZimaOS Custom App import.
- [ ] Document SSH, tmux/OMP, GUI, sync, Hermes CDP tunnel, updates and backups.
- [ ] Add health helper and run static test suite.

### Task 5: Packaging
**Files:** `tests/test_static.sh`, generated ZIP
- [ ] Add static checks for required files, no published 9222, SSH security, loopback CDP and noVNC password gate.
- [ ] Run tests.
- [ ] Commit the finished project and create a ZIP archive for handoff.
