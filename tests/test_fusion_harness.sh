#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
home="$tmp/home"
seed="$tmp/model-stack-trio.yaml"
extension="$tmp/fusion-harness.ts"
provider="$tmp/pi-commandcode-provider/index.ts"
mkdir -p "$home/.omp/agent" "$(dirname "$provider")"
printf '%s\n' '// test extension' > "$extension"
printf '%s\n' '// test provider' > "$provider"

cat > "$home/.omp/agent/config.yml" <<'YAML'
setupVersion: 2
extensions:
  - npm:pi-commandcode-provider
  - /tmp/old/pi-commandcode-provider/index.ts
  - /old-host/fusion-harness/fusion-harness.ts
  - /home/dev/.omp/extensions/keep.ts
YAML
printf '%s\n' '- name: kate' '  model: commandcode/z-ai/glm-5.3-flash' '  primary: true' '- name: ari' '  model: openai-codex/gpt-5.6-sol' '  architect: true' > "$seed"

HOME="$home" \
DEVBOX_FH_EXTENSION_PATH="$extension" \
DEVBOX_FH_PROVIDER_PATH="$provider" \
DEVBOX_FH_STACK_SOURCE="$seed" \
bash bin/enable-fusion-harness
config="$home/.omp/agent/config.yml"
stack="$home/.omp/agent/fusion-harness/model-stack-trio.yaml"

grep -Fqx "  - $provider" "$config"
grep -Fqx "  - /home/dev/.omp/extensions/keep.ts" "$config"
! grep -Fq 'npm:pi-commandcode-provider' "$config"
! grep -Fq '/tmp/old/pi-commandcode-provider/index.ts' "$config"
! grep -Fq '/old-host/fusion-harness/fusion-harness.ts' "$config"
grep -Fqx "  - $extension" "$config"
[[ "$(grep -Fc "$provider" "$config")" == 1 ]]
[[ "$(grep -Fc "$extension" "$config")" == 1 ]]

HOME="$home" \
DEVBOX_FH_EXTENSION_PATH="$extension" \
DEVBOX_FH_PROVIDER_PATH="$provider" \
DEVBOX_FH_STACK_SOURCE="$seed" \
bash bin/enable-fusion-harness
[[ "$(grep -Fc "$extension" "$config")" == 1 ]]
[[ "$(grep -Fc "$provider" "$config")" == 1 ]]

echo 'PASS: Fusion Harness extension and default stack are idempotent and container-local'
