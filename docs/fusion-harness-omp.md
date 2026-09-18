# Enable fusion-harness in OMP

This guide enables the local `fusion-harness` extension in **Oh My Pi (OMP)** for any project, while using the models and subscription accounts available in that OMP installation.

It deliberately does not assume the sample API keys or the sample model IDs shipped by the upstream repository.

## Result

After setup, this works from any project directory:

```bash
cd /path/to/project
omp
```

Inside OMP, the fusion commands are available:

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

The OMP process uses the project directory as the agents' working directory. The fusion-harness code and the default model stack are installed globally for the user; they do not need to be copied into every project.

## Devbox image integration

The `devbox` image includes the OMP-compatible extension, the
`pi-commandcode-provider` plugin, and the `yaml` runtime dependency:

```text
/opt/omp/fusion-harness/fusion-harness.ts
/opt/omp/node_modules/pi-commandcode-provider/index.ts
```

On container boot, `/usr/local/bin/enable-fusion-harness` registers those
container-local paths in the persistent OMP config without deleting unrelated
extensions. It copies the bundled stack to
`/persist/omp/agent/fusion-harness/model-stack-trio.yaml` only when the user
does not already have a stack. `omp-sync-import` runs the same normalization
after local configuration sync, so a host-only checkout path cannot remain in
the server config.

The source, tests, and stack seed live in this repository under
`extensions/fusion-harness/`, `tests/`, and
`config/fusion-harness/model-stack-trio.yaml`. The image build does not depend
on the devbox checkout being mounted into `/workspace`.

## 1. Install prerequisites

Required:

- OMP with `omp` available on `PATH`;
- Bun, used by the deterministic test suite;
- Node/npm, used to install the repository dependency;
- Git.

Check the tools:

```bash
command -v omp
command -v bun
command -v npm
git --version
omp --version
bun --version
```

Install the repository dependencies:

```bash
cd /path/to/fusion-harness-checkout
npm install
```

Use the actual checkout path if it is different.

When running inside the `devbox` image, these tools and the runtime dependency
are already installed. The checkout only needs `npm install` or `bun install`
when running the deterministic tests outside the image.

## 2. Install the Command Code provider plugin

The Command Code models in the example stack are supplied by the OMP plugin `pi-commandcode-provider`. In the `devbox` image it is already installed under `/opt/omp/node_modules`; skip the user-scope install below and verify the image-owned entrypoint instead. For a standalone OMP installation, install it at **user scope**, not only in one project:

```bash
omp plugin install pi-commandcode-provider
```

Confirm the plugin and its extension entrypoint:

```bash
omp plugin list --json
```

The JSON should contain an enabled entry similar to:

```json
{
  "name": "pi-commandcode-provider",
  "path": "/home/user/.omp/plugins/node_modules/pi-commandcode-provider",
  "manifest": { "extensions": ["./index.ts"] },
  "enabled": true
}
```

Do not copy this path literally. Use the path reported by your own OMP instance.

## 3. Authenticate using subscriptions

Start OMP:

```bash
omp
```

Run:

```text
/login
```

Select the subscription/provider that you actually use. Possible providers depend on the OMP installation and plugin set. For Command Code, choose Command Code subscription authentication rather than inventing or copying an API key.

Authentication is stored in OMP's local auth storage. Never place credentials in this guide, in a project `.env`, or in Git.

Useful checks:

```bash
omp models
omp models commandcode
omp models openai-codex
omp usage
```

`omp models --json` is the most reliable source for exact provider-qualified IDs and supported thinking levels:

```bash
omp models --json
```

## 4. Choose models for the stack

Do not copy the upstream sample IDs blindly. A stack is usable only when every selected model is:

1. listed by OMP;
2. authenticated for the current account;
3. visible to an OMP clean-room child;
4. configured with a supported thinking level.

Every YAML model must use the exact qualified form:

```yaml
model: provider/model-id
```

Examples of syntax only:

```yaml
model: commandcode/z-ai/glm-5.3-flash
model: commandcode/deepseek/deepseek-v4-flash
model: openai-codex/gpt-5.6-sol
```

The IDs above are not guarantees for another account. Copy the exact `provider` and `id` values reported by that account's OMP catalog.

Stack invariants:

- 2–5 slots;
- exactly one `architect: true` slot;
- exactly one non-architect `primary: true` slot;
- unique slot names;
- supported thinking levels;
- no duplicate colors.

## 5. Create the global stack

Create the per-user directory:

```bash
mkdir -p ~/.omp/agent/fusion-harness
```

Create the global stack file:

```bash
$EDITOR ~/.omp/agent/fusion-harness/model-stack-trio.yaml
```

Use a stack shaped like this, replacing every model with IDs from your own OMP catalog:

```yaml
- name: architect
  model: provider/architect-model-id
  thinking: medium
  architect: true
  color: "#A78BFA"

- name: main
  model: provider/main-model-id
  thinking: medium
  primary: true
  color: "#F59E0B"

- name: secondary
  model: provider/secondary-model-id
  thinking: low
  color: "#22D3EE"
```

The global file is intentionally independent from:

```text
<fusion-harness-checkout>/.pi/fusion-harness/model-stack-trio.yaml
```

Changing one does not change the other.

## 6. Register the extension globally in OMP

Find the active OMP configuration directory:

```bash
omp config path
```

The default is usually:

```text
~/.omp/agent
```

Edit the active global config:

```bash
$EDITOR ~/.omp/agent/config.yml
```

Append the extension path under the existing global `extensions` list. Use an absolute path to the checkout:

```yaml
extensions:
  - /absolute/path/to/fusion-harness-checkout/extensions/fusion-harness/fusion-harness.ts
```

If `extensions:` already exists, append the path to that list instead of creating a second `extensions` key.

Do not put this in `<project>/.omp/config.yml` if the goal is global availability.

## 7. Use a version with OMP child compatibility

OMP is not CLI-compatible with Pi in three relevant areas:

- OMP launch-mode `-e` expects a file path; `npm:pi-commandcode-provider` must be resolved to the plugin's absolute `index.ts` entrypoint for OMP children;
- OMP does not accept Pi's `--no-context-files` or synthetic `--session-id` flags;
- OMP calls the filesystem search tool `glob`, not Pi's `find`/`ls` tool names.

The OMP-compatible fusion-harness implementation must therefore:

- load the Command Code extension explicitly inside OMP clean-room children;
- use `omp models --json` for OMP child catalog checks;
- omit unsupported OMP flags;
- let OMP create the first child session and use `--session` only to resume it;
- translate `find`/`ls` to `glob` in OMP tool allowlists;
- normalize OMP's system-prompt section array before rendering `/fh-system-prompt`.

Before deploying a fresh checkout, verify that its `extensions/fusion-harness/modules/child-runner.ts` contains OMP-aware handling for these cases. A plain upstream checkout without these changes may load `/fh` but every child can fail with errors such as:

```text
unknown flags: --no-context-files, --session-id
Unknown tool in --tools: ls
Failed to load extension .../npm:pi-commandcode-provider
```

If the checkout does not contain the compatibility changes, use the maintained fork/branch containing them or have an agent apply the OMP compatibility changes before installing the extension globally.

## 8. Restart OMP

Global extension settings are read at process startup. Close the existing OMP session completely and start a new one from the project being edited:

```bash
cd /path/to/project
omp
```

You should not need to enter the fusion-harness checkout and should not need `-e` or `--fh-config` for the default global stack.

The extension uses:

```text
~/.omp/agent/fusion-harness/model-stack-trio.yaml
```

when OMP starts without an explicit `--fh-config`.

## 9. Verify without immediately spending model requests

Inside the new OMP session:

```text
/fh
```

Expected: the fusion-harness command index.

Then:

```text
/fh on
```

Expected: one model-bar row per slot, including role, slot name, model, thinking level, context, TPS, and cost.

Then:

```text
/fh-system-prompt
```

Expected: one effective system-prompt column per configured slot.

These checks exercise registration, stack loading, and rendering. They do not need a model generation.

## 10. Run a paid/subscription smoke test

A single-slot test limits usage to one model:

```text
/fh-only <slot-name> Reply with exactly OK.
```

For example, if the YAML uses `main`:

```text
/fh-only main Reply with exactly OK.
```

Then test the full fan-out only when you are ready to use all configured models:

```text
/fh-opinion Compare SQLite and PostgreSQL for a local single-user application.
```

`/fh-opinion` sends a request to every configured slot. Subscription usage and provider quotas remain authoritative; a displayed cost of zero from a custom provider is not proof that upstream usage is free.

## 11. Per-project overrides

The global configuration is the default. A specific project can override it for one launch:

```bash
omp \
  -e /absolute/path/to/fusion-harness/extensions/fusion-harness/fusion-harness.ts \
  --fh-config /absolute/path/to/project-stack.yaml
```

The explicit `--fh-config` path wins over the global stack. This is useful when different projects need different model combinations.

## Troubleshooting

### `/fh` is missing

The current OMP process was probably started before the global extension was added. Close it and restart OMP. Then check:

```bash
omp config path
omp plugin list --json
```

For a one-session diagnostic, load the extension explicitly:

```bash
omp \
  -e /absolute/path/to/fusion-harness/extensions/fusion-harness/fusion-harness.ts \
  --fh-config ~/.omp/agent/fusion-harness/model-stack-trio.yaml
```

### `model is not registered`

The provider/model ID in YAML does not exactly match OMP's catalog. Compare it with:

```bash
omp models --json
```

Correct the provider prefix, spelling, punctuation, and model ID.

### `not visible to clean-room children`

For Command Code, identify the user plugin path:

```bash
omp plugin list --json
```

Then verify the plugin can be loaded explicitly by OMP:

```bash
omp --no-extensions \
  -e /absolute/path/to/pi-commandcode-provider/index.ts \
  models --json commandcode
```

If that catalog does not contain the configured model, the child cannot use it.

### `no configured authentication`

Authenticate the provider in OMP with `/login`. Do not solve a subscription setup problem by copying sample API keys from the repository.

### `Failed to load extension .../npm:pi-commandcode-provider`

That is an OMP launch-mode path-resolution problem. OMP children need the absolute plugin entrypoint, normally:

```text
~/.omp/plugins/node_modules/pi-commandcode-provider/index.ts
```

Use the actual path from `omp plugin list --json`.

### `unknown flags: --no-context-files, --session-id`

The child runner is still using Pi-only flags. Update to an OMP-compatible fusion-harness checkout.

### `Unknown tool in --tools: find` or `ls`

The child runner is passing Pi tool names to OMP. Update to a version that maps `find`/`ls` to OMP's `glob` tool.

### Startup is slow

OMP may be connecting configured MCP servers before the interactive session settles. This is independent of fusion-harness. For a diagnostic run only:

```bash
OMP_MCP_TIMEOUT_MS=1000 omp
```

Do not treat a short MCP timeout as a production requirement; it can disable MCP tools that your project expects.

## `/install` and `/prime`

If OMP shows `/install` and `/prime`, those commands come from the repository's `.claude/commands/` Markdown files:

- `/install` describes prerequisite, dependency, credential, test, and launch checks;
- `/prime` gives an agent architectural context about fusion-harness.

They are not the fusion runtime. The `/fh-*` commands are registered by `fusion-harness.ts` only after the extension is loaded.

The original `/install` text mentions the upstream API-key sample stacks. For subscription-based OMP installations, use this guide's `/login`, `omp models`, and clean-room checks instead.

## Preserve and publish local changes

This setup depends on the OMP compatibility changes in the current fusion-harness checkout. `git status` may show changes to:

- `extensions/fusion-harness/fusion-harness.ts`;
- `extensions/fusion-harness/modules/child-runner.ts`;
- `extensions/fusion-harness/modules/model-stack.ts`;
- `extensions/fusion-harness/modules/runtime.ts`;
- the harness tests;
- a personal stack YAML.

Before reusing the setup on another machine, preserve the code changes in a commit or publish them to a branch/fork. Do not commit `auth.json`, `.env`, or any credential material.

Validation for the maintained OMP-compatible checkout:

```bash
npm test
git diff --check
```

The deterministic suite must pass before installing the extension globally on another OMP instance.
