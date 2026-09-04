# syntax=docker/dockerfile:1.7

ARG BUN_VERSION=1.3.14
ARG NODE_MAJOR=24
ARG TREE_SITTER_CLI_VERSION=0.25.10
ARG COMMANDCODE_PROVIDER_VERSION=0.4.2
ARG YAML_VERSION=2.9.0
ARG CHROME_DEVTOOLS_MCP_VERSION=1.6.0

FROM golang:bookworm AS orca-builder
RUN mkdir -p /out && GOBIN=/out go install github.com/orca-cli/orca/cmd/orca@latest

FROM oven/bun:${BUN_VERSION}-debian AS bun-source

FROM node:${NODE_MAJOR}-bookworm

ARG OMP_VERSION=latest
ARG TARGETARCH
ARG COMMANDCODE_PROVIDER_VERSION
ARG YAML_VERSION
ARG TREE_SITTER_CLI_VERSION
ARG CHROME_DEVTOOLS_MCP_VERSION
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Europe/Rome \
    DISPLAY=:99 \
    XDG_CONFIG_HOME=/persist/config \
    XDG_DATA_HOME=/persist/data \
    GIT_CONFIG_GLOBAL=/persist/gitconfig \
    PI_CONFIG_FILES=/etc/devbox/omp-server.yml \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    CHROME_USER_DATA_DIR=/persist/chromium \
    CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS=1 \
    PATH=/opt/omp/node_modules/.bin:/usr/local/go/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

COPY --from=bun-source /usr/local/bin/bun /usr/local/bin/bun
COPY --from=orca-builder /usr/local/go /usr/local/go
RUN ln -sf /usr/local/bin/bun /usr/local/bin/bunx

RUN apt-get update && apt-get install -y --no-install-recommends \
      openssh-server sudo gosu tmux \
      git gh git-lfs ripgrep rsync fd-find xclip \
      curl wget ca-certificates gnupg jq unzip zip \
      build-essential make cmake pkg-config \
      python3 python3-pip python3-venv \
      chromium xvfb openbox x11vnc novnc websockify \
      dbus-x11 xdg-utils fonts-liberation fonts-dejavu-core \
      procps iproute2 lsof less nano vim \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /run/sshd /opt/omp /etc/devbox/fusion-harness \
    && ln -sf /usr/bin/fdfind /usr/local/bin/fd

# Kickstart.nvim tracks the latest stable Neovim. Debian stable is normally
# behind, so install the official stable tarball for the image architecture.
RUN set -eux; \
    case "${TARGETARCH}" in \
      amd64) nvim_arch="x86_64" ;; \
      arm64) nvim_arch="arm64" ;; \
      *) echo "Unsupported TARGETARCH for Neovim: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL "https://github.com/neovim/neovim/releases/latest/download/nvim-linux-${nvim_arch}.tar.gz" -o /tmp/nvim.tar.gz; \
    rm -rf "/opt/nvim-linux-${nvim_arch}"; \
    tar -C /opt -xzf /tmp/nvim.tar.gz; \
    rm /tmp/nvim.tar.gz; \
    ln -sfn "/opt/nvim-linux-${nvim_arch}/bin/nvim" /usr/local/bin/nvim; \
    nvim --version | head -n 1

# Kickstart's current config uses Neovim's built-in vim.pack and expects the
# tree-sitter CLI. Seed the config in the image; entrypoint copies it to
# persistent storage only on first use so user edits are never overwritten.
RUN npm install --global "tree-sitter-cli@${TREE_SITTER_CLI_VERSION}" \
    && tree-sitter --version \
    && git clone --depth 1 https://github.com/nvim-lua/kickstart.nvim.git /opt/kickstart.nvim \
    && test -f /opt/kickstart.nvim/init.lua

# Install OMP and its built-in devbox extensions in an image-owned path.
WORKDIR /opt/omp
RUN printf '{"private":true}\n' > package.json \
    && bun add "@oh-my-pi/pi-coding-agent@${OMP_VERSION}" \
        "pi-commandcode-provider@${COMMANDCODE_PROVIDER_VERSION}" \
        "yaml@${YAML_VERSION}" \
    && test -x /opt/omp/node_modules/.bin/omp \
    && test -f /opt/omp/node_modules/pi-commandcode-provider/index.ts \
    && test -f /opt/omp/node_modules/yaml/dist/index.js

COPY extensions/fusion-harness /opt/omp/fusion-harness
COPY config/fusion-harness/model-stack-trio.yaml /etc/devbox/fusion-harness/model-stack-trio.yaml

# OMP currently reaches the shared graphical Chromium through MCP. Pin the MCP
# package in the image so sessions do not download a moving `latest` at runtime.
RUN npm install --global "chrome-devtools-mcp@${CHROME_DEVTOOLS_MCP_VERSION}" \
    && chrome-devtools-mcp --help >/dev/null

COPY --from=orca-builder /out/orca /usr/local/bin/orca

# node:24-bookworm already provides node:node with UID/GID 1000. Reuse it for
# the persistent dev account instead of attempting to allocate UID/GID 1000 twice.
# The base node account has a locked shadow entry (!); '*' keeps password login
# impossible but makes the account valid for SSH public-key authentication.
RUN groupmod --new-name dev node \
    && usermod --login dev --home /home/dev --move-home --shell /bin/bash --gid dev node \
    && usermod --password '*' dev \
    && printf 'dev ALL=(ALL) NOPASSWD:ALL\n' > /etc/sudoers.d/devbox \
    && chmod 0440 /etc/sudoers.d/devbox

COPY config/sshd_config /etc/ssh/sshd_config
COPY config/omp-server.yml /etc/devbox/omp-server.yml
COPY config/omp-devbox-mcp.json /etc/devbox/omp-devbox-mcp.json
COPY bin/ /usr/local/bin/
RUN chmod +x /usr/local/bin/browser-service \
             /usr/local/bin/browser-gui \
             /usr/local/bin/omp-sync-import \
             /usr/local/bin/enable-fusion-harness \
             /usr/local/bin/devbox-health \
             /usr/local/bin/omp-session \
             /usr/local/bin/omp-raw \
             /usr/local/bin/omp-update \
             /usr/local/bin/orca-update \
             /usr/local/bin/entrypoint

WORKDIR /workspace
EXPOSE 22 6080
ENTRYPOINT ["/usr/local/bin/entrypoint"]
