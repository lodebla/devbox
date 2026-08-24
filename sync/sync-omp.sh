#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE="${1:-devbox}"
LOCAL_OMP="${OMP_HOME:-$HOME/.omp}"
REMOTE_TMP="/tmp/omp-sync-${USER:-user}-$$.tar.gz"

[[ -d "$LOCAL_OMP" ]] || { echo "OMP directory not found: $LOCAL_OMP" >&2; exit 2; }
command -v ssh >/dev/null || { echo "ssh is required" >&2; exit 2; }
command -v scp >/dev/null || { echo "scp is required" >&2; exit 2; }
command -v tar >/dev/null || { echo "tar is required" >&2; exit 2; }

tmp="$(mktemp -t omp-sync.XXXXXX.tar.gz)"
trap 'rm -f "$tmp"' EXIT

parent="$(dirname "$LOCAL_OMP")"
base="$(basename "$LOCAL_OMP")"

tar -czf "$tmp" \
  --exclude='*/agent.db' \
  --exclude='*/agent.db-*' \
  --exclude='*/.env' \
  --exclude='*/sessions' \
  --exclude='*/blobs' \
  --exclude='*/logs' \
  --exclude='*/auth-broker.token' \
  --exclude='*/auth-gateway.token' \
  --exclude='*/node_modules' \
  -C "$parent" "$base"
echo "Uploading sanitized OMP config to $REMOTE..."
scp "$tmp" "${REMOTE}:${REMOTE_TMP}"
ssh "$REMOTE" "omp-sync-import '$REMOTE_TMP'; rm -f '$REMOTE_TMP'"
echo "Done."
