#!/bin/bash
# First boot of the monitoring EC2 (arm64): Docker + Compose.
set -euxo pipefail

dnf install -y docker
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL https://github.com/docker/compose/releases/download/v2.40.3/docker-compose-linux-aarch64 \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

systemctl enable --now docker
mkdir -p /opt/enervision
