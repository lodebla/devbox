#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

fail() { echo "FAIL: $*" >&2; exit 1; }
pass() { echo "PASS: $*"; }

for f in Dockerfile config/sshd_config config/omp-server.yml config/omp-devbox-mcp.json bin/entrypoint bin/browser-service bin/browser-gui bin/omp-sync-import sync/sync-omp.sh sync/sync-omp.ps1 zimaos-compose.yml GUIDA-ZIMAOS.md; do
  [[ -f "$f" ]] || fail "missing $f"
done
pass "required files exist"

# node:24-bookworm already ships node:node as UID/GID 1000. The dev user must
# reuse/rename it instead of trying to create a second UID/GID 1000.
grep -q 'groupmod --new-name dev node' Dockerfile || fail "Dockerfile does not reuse the base node group"
grep -q 'usermod --login dev' Dockerfile || fail "Dockerfile does not reuse the base node user"
grep -Fq "usermod --password '*' dev" Dockerfile || fail "dev account is left locked for SSH public-key login"
! grep -q 'groupadd --gid 1000 dev' Dockerfile || fail "Dockerfile tries to recreate occupied GID 1000"
pass "base node UID/GID reuse and SSH account state"

for f in bin/entrypoint bin/browser-service bin/browser-gui bin/omp-sync-import bin/devbox-health bin/omp-session bin/omp-raw bin/omp-update bin/orca-update sync/sync-omp.sh tests/test_static.sh; do
  bash -n "$f" || fail "bash syntax: $f"
done
pass "bash syntax"

! grep -Eq '(^|["[:space:]])9222:9222' zimaos-compose.yml || fail "CDP 9222 must not be published"
! grep -Eq "published:[[:space:]]*['\"]?9222" zimaos-compose.yml || fail "CDP 9222 must not be published"
pass "CDP is not published"

grep -q 'enabled: false' config/omp-server.yml || fail "released OMP built-in browser must be disabled in server overlay"
grep -q -- '--browser-url=http://127.0.0.1:9222' config/omp-devbox-mcp.json || fail "Chrome DevTools MCP is not pointed at loopback CDP"
grep -q 'chrome-devtools-mcp' Dockerfile || fail "Chrome DevTools MCP is not installed"
grep -q 'omp-devbox-mcp.json /home/dev/.cursor/mcp.json' bin/entrypoint || fail "server MCP discovery shim missing"
pass "OMP shared-browser MCP wiring"

grep -q -- '--remote-debugging-address="$CDP_HOST"' bin/browser-service || fail "Chromium debugging address is not explicit"
grep -q 'CDP_HOST="127.0.0.1"' bin/browser-service || fail "Chromium CDP host is not loopback"
pass "loopback CDP invariant"

grep -q '^PermitRootLogin no' config/sshd_config || fail "root SSH login not disabled"
grep -q '^PasswordAuthentication no' config/sshd_config || fail "SSH password login not disabled"
grep -q '^AllowTcpForwarding yes' config/sshd_config || fail "SSH forwarding required for Hermes"
pass "SSH security/tunnel settings"

grep -q 'require_password' bin/browser-gui || fail "GUI password gate missing"
grep -q -- '-rfbauth "$PASSFILE"' bin/browser-gui || fail "x11vnc password auth missing"
pass "GUI password gate"

grep -q 'agent.db' sync/sync-omp.sh || fail "sync does not exclude agent.db"
grep -q 'node_modules' sync/sync-omp.sh || fail "sync does not exclude node_modules"
grep -q 'agent.db' sync/sync-omp.ps1 || fail "PowerShell sync does not exclude agent.db"
pass "sync exclusions"

grep -q 'PI_CONFIG_FILES=/etc/devbox/omp-server.yml' Dockerfile || fail "server config overlay env missing"
pass "server overlay separation"

grep -q 'chown dev:dev /persist /persist/omp' bin/entrypoint || fail "persistent top-level dirs are not repaired each boot"
grep -q '^chmod 755 /persist$' bin/entrypoint || fail "/persist permissions are unsafe for sshd StrictModes"
pass "persistent directory ownership and SSH-safe permissions"

bash tests/test_sync_import.sh

echo "All static tests passed."
