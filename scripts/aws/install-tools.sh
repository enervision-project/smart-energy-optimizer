#!/usr/bin/env bash
# Installs into ~/.local (no sudo): AWS CLI v2, Terraform and GitHub CLI (gh).
# Also adds `export AWS_PROFILE=enervision` to ~/.bashrc (profile created by `aws configure sso`).
# Usage: scripts/aws/install-tools.sh
set -euo pipefail

bin=$HOME/.local/bin
mkdir -p "$bin"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

arch=$(uname -m)
case $arch in
  x86_64) a=amd64 ;;
  aarch64) a=arm64 ;;
  *) echo "unsupported architecture: $arch" >&2; exit 1 ;;
esac

json_field() { python3 -c "import json, sys; print(json.load(sys.stdin)['$1'])"; }

echo "== AWS CLI v2"
curl -fsSLo "$tmp/awscli.zip" "https://awscli.amazonaws.com/awscli-exe-linux-$arch.zip"
unzip -q "$tmp/awscli.zip" -d "$tmp"
"$tmp/aws/install" -i "$HOME/.local/aws-cli" -b "$bin" --update

echo "== Terraform"
tfv=$(curl -fsS https://checkpoint-api.hashicorp.com/v1/check/terraform | json_field current_version) || tfv=1.13.3
curl -fsSLo "$tmp/tf.zip" "https://releases.hashicorp.com/terraform/$tfv/terraform_${tfv}_linux_$a.zip"
unzip -o -q "$tmp/tf.zip" terraform -d "$bin"

echo "== GitHub CLI (gh)"
ghv=$(curl -fsS https://api.github.com/repos/cli/cli/releases/latest | json_field tag_name) || ghv=v2.62.0
ghv=${ghv#v}
curl -fsSL "https://github.com/cli/cli/releases/download/v$ghv/gh_${ghv}_linux_$a.tar.gz" | tar -xz -C "$tmp"
install -m 755 "$tmp/gh_${ghv}_linux_$a/bin/gh" "$bin/gh"

if ! grep -q 'AWS_PROFILE=enervision' "$HOME/.bashrc"; then
  echo 'export AWS_PROFILE=enervision' >>"$HOME/.bashrc"
  echo "== added to ~/.bashrc: export AWS_PROFILE=enervision"
fi

echo
"$bin/aws" --version
"$bin/terraform" version | head -n1
"$bin/gh" --version | head -n1
echo
echo "OK. Open a new terminal (or run: source ~/.bashrc), then sign in with: aws configure sso && gh auth login"
