#!/usr/bin/env bash
#
# Deploy the current branch tip onto this machine. Run as root:
#
#   ssh vps 'sudo /opt/gazette/deploy/update.sh'
#
# Root is needed for systemctl; the checkout and the build run as the service
# account. Visitors are unaffected while this runs — Caddy keeps serving the
# previously rendered pages, and the process only stops for the few seconds it
# takes to refetch the feeds.
#
# Environment:
#   BRANCH    branch to deploy  (default: main)
#   APP_DIR   install prefix    (default: /opt/gazette)
#   APP_USER  service account   (default: gazette)

set -euo pipefail

BRANCH="${BRANCH:-main}"
APP_DIR="${APP_DIR:-/opt/gazette}"
APP_USER="${APP_USER:-gazette}"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31mxx\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die 'must run as root (needed for systemctl)'
[[ -d $APP_DIR/.git ]] || die "no git checkout in $APP_DIR — run bootstrap.sh first"

as_app() { runuser -u "$APP_USER" -- env HOME="$APP_DIR" PATH="$PATH" "$@"; }

cd "$APP_DIR"

before=$(as_app git rev-parse HEAD)

log "Fetching origin/$BRANCH"
as_app git fetch --quiet origin "$BRANCH"

# reset --hard, not pull: building rewrites files that git tracks (static/sw.js,
# the .min.* outputs, and the .br/.gz siblings of every asset), so a pull would
# refuse to run over "local changes". Discarding them is exactly right — they are
# build output and get regenerated below.
log 'Resetting to the fetched revision'
as_app git reset --quiet --hard "origin/$BRANCH"

after=$(as_app git rev-parse HEAD)
if [[ $before == "$after" ]]; then
	log "Already at ${after:0:8} — rebuilding and restarting anyway"
else
	log "${before:0:8} -> ${after:0:8}"
fi

log 'Syncing dependencies'
as_app uv sync --exact --no-default-groups --group build --compile-bytecode

log 'Rebuilding static assets'
# compress_all.py first: it produces static/css/style.min.css and
# static/js/index.min.js, whose hashes generate_opml.py needs to render its pages.
as_app ./.venv/bin/python build_tools/compress_all.py
as_app ./.venv/bin/python build_tools/generate_opml.py

# If the shipped Caddyfile changed, the operator has to reconcile it by hand: the
# installed copy carries a substituted domain and root, so blindly overwriting it
# would clobber those.
if ! diff -q <(sed -e 's#^[a-z0-9.-]* {#SITE {#' -e 's#root \* .*#root * DIR#' deploy/Caddyfile) \
	<(sed -e 's#^[a-z0-9.-]* {#SITE {#' -e 's#root \* .*#root * DIR#' /etc/caddy/Caddyfile) \
	>/dev/null 2>&1; then
	log 'NOTE: deploy/Caddyfile differs from /etc/caddy/Caddyfile — reconcile manually'
fi

log 'Restarting gazette'
# Note the render timestamp so we can tell the new pages from the old ones.
prev_render=$(stat -c %Y "$APP_DIR/static/index.html" 2>/dev/null || echo 0)
systemctl restart gazette

log 'Waiting for the new render'
for _ in $(seq 1 90); do
	now=$(stat -c %Y "$APP_DIR/static/index.html" 2>/dev/null || echo 0)
	[[ $now -gt $prev_render ]] && break
	systemctl is-active --quiet gazette || break
	sleep 1
done

if ! systemctl is-active --quiet gazette; then
	printf '\033[1;31mxx\033[0m service is not running:\n' >&2
	journalctl -u gazette --no-pager --lines=30 >&2
	exit 1
fi

now=$(stat -c %Y "$APP_DIR/static/index.html" 2>/dev/null || echo 0)
if [[ $now -gt $prev_render ]]; then
	log "Deployed ${after:0:8} — pages regenerated"
else
	log "Service is up but index.html is unchanged; check: journalctl -u gazette -n 30"
fi
