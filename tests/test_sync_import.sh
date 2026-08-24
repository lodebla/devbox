#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
src="$tmp/src/.omp"
home="$tmp/home"
mkdir -p \
  "$src/agent/skills/demo" \
  "$src/profiles/work/agent/skills/profile-skill" \
  "$src/plugins/node_modules/local-only" \
  "$home/.omp/agent/sessions" \
  "$home/.omp/profiles/work/agent"

printf 'name: demo\n' > "$src/agent/skills/demo/SKILL.md"
printf 'theme: synced\n' > "$src/profiles/work/agent/config.yml"
printf 'profile skill\n' > "$src/profiles/work/agent/skills/profile-skill/SKILL.md"
printf 'LOCAL-DEFAULT-SECRET\n' > "$src/agent/agent.db"
printf 'LOCAL-PROFILE-SECRET\n' > "$src/profiles/work/agent/agent.db"
printf 'LOCAL-MODULE\n' > "$src/plugins/node_modules/local-only/value"

printf 'SERVER-DEFAULT-SECRET\n' > "$home/.omp/agent.db.placeholder"
mkdir -p "$home/.omp/agent"
printf 'SERVER-DEFAULT-SECRET\n' > "$home/.omp/agent/agent.db"
printf 'SERVER-PROFILE-SECRET\n' > "$home/.omp/profiles/work/agent/agent.db"
printf 'KEEP-SESSION\n' > "$home/.omp/agent/sessions/keep.txt"
mkdir -p "$home/.omp/plugins/node_modules/server-only"
printf 'SERVER-MODULE\n' > "$home/.omp/plugins/node_modules/server-only/value"
printf 'delete me\n' > "$home/.omp/obsolete.txt"

tar -czf "$tmp/sync.tar.gz" -C "$tmp/src" .omp
HOME="$home" bash bin/omp-sync-import "$tmp/sync.tar.gz" >/dev/null

[[ -f "$home/.omp/agent/skills/demo/SKILL.md" ]]
[[ -f "$home/.omp/profiles/work/agent/config.yml" ]]
[[ -f "$home/.omp/profiles/work/agent/skills/profile-skill/SKILL.md" ]]
[[ "$(cat "$home/.omp/agent/agent.db")" == 'SERVER-DEFAULT-SECRET' ]]
[[ "$(cat "$home/.omp/profiles/work/agent/agent.db")" == 'SERVER-PROFILE-SECRET' ]]
[[ "$(cat "$home/.omp/agent/sessions/keep.txt")" == 'KEEP-SESSION' ]]
[[ "$(cat "$home/.omp/plugins/node_modules/server-only/value")" == 'SERVER-MODULE' ]]
[[ ! -e "$home/.omp/plugins/node_modules/local-only/value" ]]
[[ ! -e "$home/.omp/obsolete.txt" ]]

echo 'PASS: full ~/.omp sync preserves server runtime/auth exclusions and supports named profiles'
