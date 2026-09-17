#!/usr/bin/env bash
#
# One-time provisioning of a Debian/Ubuntu VPS for Gazette. Run as root.
#
#   DOMAIN=insoumis.news ./deploy/bootstrap.sh
#
# Safe to re-run: every step checks whether it already applies. Day-to-day
# deployments go through update.sh instead.
#
# Environment:
#   DOMAIN               site address written into the Caddyfile (required)
#   REPO_URL             git remote to clone      (default: haysberg/gazette)
#   BRANCH               branch to track          (default: main)
#   APP_DIR              install prefix           (default: /opt/gazette)
#   APP_USER             service account          (default: gazette)
#   SKIP_CADDY_INSTALL   set to 1 to manage Caddy yourself

set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/haysberg/gazette.git}"
BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/gazette}"
APP_USER="${APP_USER:-gazette}"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die 'must run as root'
[[ -n "${DOMAIN:-}" ]] || die 'DOMAIN is required, e.g. DOMAIN=insoumis.news ./deploy/bootstrap.sh'

# Runs a command as the service account. runuser comes from util-linux, so it is
# there even on a minimal image where sudo is not. HOME has to be explicit: uv
# stores its cache and its managed Python interpreters under it.
as_app() { runuser -u "$APP_USER" -- env HOME="$APP_DIR" PATH="$PATH" "$@"; }

log 'Installing base packages'
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq --no-install-recommends ca-certificates curl git

if ! command -v uv >/dev/null 2>&1; then
	log 'Installing uv into /usr/local/bin'
	# uv brings its own Python 3.14, so no deadsnakes/PPA dance is needed.
	curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh
else
	log "uv already present ($(uv --version))"
fi

if id -u "$APP_USER" >/dev/null 2>&1; then
	log "User $APP_USER already exists"
else
	log "Creating system user $APP_USER"
	useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

if [[ -d $APP_DIR/.git ]]; then
	log "Repository already cloned in $APP_DIR"
else
	log "Cloning $REPO_URL into $APP_DIR"
	# useradd --create-home already populated $APP_DIR from /etc/skel, and git
	# refuses to clone into a non-empty directory — so clone aside and move the
	# contents in. Done as root because $APP_USER cannot write to /opt; the
	# chown below hands the whole tree back to it.
	tmp=$(mktemp -d)
	git clone --quiet --branch "$BRANCH" "$REPO_URL" "$tmp/repo"
	# dotglob so .git and .github come across too.
	(shopt -s dotglob && mv "$tmp/repo"/* "$APP_DIR"/)
	rm -rf "$tmp"
fi

# Caddy runs as its own user and only needs to traverse the tree to read static/.
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chmod 755 "$APP_DIR"

cd "$APP_DIR"

log 'Installing Python dependencies (runtime + build group)'
# --no-default-groups is what actually excludes dev; --no-dev is silently ignored
# when a --group is also passed. That keeps Pillow and cairosvg, and therefore
# libcairo, off this machine.
as_app uv sync --exact --no-default-groups --group build --compile-bytecode

log 'Building static assets'
# Order matters: compress_all.py emits static/css/style.min.css and
# static/js/index.min.js, whose hashes generate_opml.py renders into its pages.
# .venv/bin/python rather than `uv run`: the latter re-syncs the environment with
# the default groups and would pull the dev group back in.
as_app ./.venv/bin/python build_tools/compress_all.py
as_app ./.venv/bin/python build_tools/generate_opml.py

log 'Installing systemd unit'
install -m 644 deploy/gazette.service /etc/systemd/system/gazette.service
systemctl daemon-reload
systemctl enable gazette
systemctl restart gazette

if [[ "${SKIP_CADDY_INSTALL:-0}" != 1 ]] && ! command -v caddy >/dev/null 2>&1; then
	log 'Installing Caddy from the official repository'
	apt-get install -y -qq --no-install-recommends debian-keyring debian-archive-keyring apt-transport-https
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
		| gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
	curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
		| tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
	apt-get update -qq
	apt-get install -y -qq caddy
fi

if command -v caddy >/dev/null 2>&1; then
	log "Installing Caddyfile for $DOMAIN"
	if [[ -f /etc/caddy/Caddyfile && ! -f /etc/caddy/Caddyfile.pre-gazette ]]; then
		cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.pre-gazette
		log 'Previous Caddyfile saved as /etc/caddy/Caddyfile.pre-gazette'
	fi
	install -d -m 755 /etc/caddy
	sed -e "s#^insoumis\.news {#${DOMAIN} {#" \
		-e "s#root \* /opt/gazette/static#root * ${APP_DIR}/static#" \
		deploy/Caddyfile > /etc/caddy/Caddyfile
	caddy validate --adapter caddyfile --config /etc/caddy/Caddyfile
	systemctl reload caddy || systemctl restart caddy
else
	warn 'Caddy not installed; copy deploy/Caddyfile yourself and adjust the domain'
fi

log 'Waiting for the first render'
for _ in $(seq 1 60); do
	[[ -f $APP_DIR/static/index.html ]] && break
	sleep 1
done

if [[ -f $APP_DIR/static/index.html ]]; then
	log "Done. Site should be live at https://${DOMAIN}/"
else
	warn 'index.html was not produced yet — check: journalctl -u gazette -n 50'
fi

systemctl --no-pager --lines=0 status gazette || true
