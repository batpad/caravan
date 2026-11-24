#!/usr/bin/env bash
# Caravan Road — idempotent deploy for Debian (12/13+) behind nginx + gunicorn.
#
#   git pull && sudo ./deploy/deploy.sh                 # first install or update
#   sudo ./deploy/deploy.sh --email you@example.com     # first install with a Let's Encrypt contact
#   sudo ./deploy/deploy.sh --no-tls                    # HTTP only (e.g. TLS terminated elsewhere)
#
# Run it from any checkout of the repo. It copies the code into /srv/caravan/app, so the
# running app never depends on the checkout and everything it uses is owned by "caravan".
set -euo pipefail

DOMAIN="${CARAVAN_DOMAIN:-caravan.whydidweevendothis.com}"
APP_USER="caravan"
APP_HOME="/srv/caravan"
EMAIL=""
TLS=1
SKIP_APT=0

usage() { sed -n '2,10p' "$0"; exit "${1:-0}"; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2 ;;
    --email) EMAIL="$2"; shift 2 ;;
    --no-tls) TLS=0; shift ;;
    --skip-apt) SKIP_APT=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
done

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo $0)" >&2; exit 1; }

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEPLOY="$SRC/deploy"
APP="$APP_HOME/app"
VENV="$APP_HOME/venv"
ENV_FILE="/etc/caravan/caravan.env"
SNIPPET="/etc/nginx/snippets/caravan-app.conf"
SITE="/etc/nginx/sites-available/caravan.conf"
CERT="/etc/letsencrypt/live/$DOMAIN/fullchain.pem"

step() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
render() {  # render TEMPLATE DEST
  sed -e "s|__DOMAIN__|$DOMAIN|g" -e "s|__APP_HOME__|$APP_HOME|g" -e "s|__NGINX_APP_SNIPPET__|$SNIPPET|g" "$1" > "$2"
}
as_app() { runuser -u "$APP_USER" -- "$@"; }
manage() {  # run manage.py as the app user with the production environment loaded
  as_app bash -c 'set -a; . "$0"; set +a; cd "$1"; shift; exec "$@"' \
    "$ENV_FILE" "$APP" "$VENV/bin/python" manage.py "$@"
}

# ---------------------------------------------------------------------------------------------
if [[ $SKIP_APT -eq 0 ]]; then
  step "Installing system packages"
  pkgs=(python3 python3-venv rsync nginx sqlite3 curl)
  [[ $TLS -eq 1 ]] && pkgs+=(certbot)
  missing=()
  for p in "${pkgs[@]}"; do dpkg -s "$p" &>/dev/null || missing+=("$p"); done
  if [[ ${#missing[@]} -gt 0 ]]; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}"
  else
    echo "all present"
  fi
fi

step "Ensuring user '$APP_USER' and directories"
if ! id "$APP_USER" &>/dev/null; then
  adduser --system --group --home "$APP_HOME" --shell /usr/sbin/nologin "$APP_USER"
fi
install -d -o "$APP_USER" -g "$APP_USER" -m 0751 "$APP_HOME"
install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$APP" "$APP_HOME/data"
install -d -o "$APP_USER" -g "$APP_USER" -m 0755 "$APP_HOME/static"
install -d -o root -g "$APP_USER" -m 0750 /etc/caravan
install -d -m 0755 /var/www/letsencrypt

step "Syncing code to $APP"
rsync -a --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude 'db.sqlite3*' --exclude 'staticfiles/' --exclude '.DS_Store' --exclude '*.pdf' \
  "$SRC/" "$APP/"
chown -R "$APP_USER:$APP_USER" "$APP"
chmod -R go-w "$APP"

step "Python virtualenv"
if [[ ! -x "$VENV/bin/python" ]]; then
  install -d -o "$APP_USER" -g "$APP_USER" -m 0750 "$VENV"
  as_app python3 -m venv "$VENV"
fi
as_app "$VENV/bin/pip" install -q --upgrade pip
as_app "$VENV/bin/pip" install -q -r "$APP/requirements.txt"

step "Environment file $ENV_FILE"
if [[ ! -f "$ENV_FILE" ]]; then
  SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')"
  SCHEME=$([[ $TLS -eq 1 ]] && echo https || echo http)
  cat > "$ENV_FILE" <<EOF
DJANGO_SECRET_KEY=$SECRET
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=$DOMAIN
DJANGO_CSRF_TRUSTED_ORIGINS=$SCHEME://$DOMAIN
CARAVAN_HTTPS=$([[ $TLS -eq 1 ]] && echo true || echo false)
CARAVAN_DB_PATH=$APP_HOME/data/db.sqlite3
CARAVAN_STATIC_ROOT=$APP_HOME/static
DJANGO_LOG_LEVEL=WARNING
EOF
  echo "created (secret key generated)"
else
  echo "kept existing"
fi
chown root:"$APP_USER" "$ENV_FILE"
chmod 0640 "$ENV_FILE"

step "Django: migrate, collectstatic, checks"
manage migrate --noinput
manage collectstatic --noinput --clear -v0
as_app "$VENV/bin/python" -m compileall -q "$APP" >/dev/null || true
manage check --deploy --fail-level ERROR || { echo "Django deploy check failed" >&2; exit 1; }

step "systemd units"
install -m 0644 "$DEPLOY/caravan.socket" /etc/systemd/system/caravan.socket
render "$DEPLOY/caravan.service" /etc/systemd/system/caravan.service
render "$DEPLOY/caravan-cleanup.service" /etc/systemd/system/caravan-cleanup.service
install -m 0644 "$DEPLOY/caravan-cleanup.timer" /etc/systemd/system/caravan-cleanup.timer
systemctl daemon-reload
systemctl enable --now caravan.socket caravan-cleanup.timer
systemctl enable caravan.service
systemctl restart caravan.service

step "nginx site for $DOMAIN"
install -d /etc/nginx/snippets
render "$DEPLOY/nginx-app.snippet.tmpl" "$SNIPPET"
write_site() {
  if [[ $TLS -eq 1 && -f "$CERT" ]]; then
    render "$DEPLOY/nginx-https.conf.tmpl" "$SITE"
  else
    render "$DEPLOY/nginx-http.conf.tmpl" "$SITE"
  fi
  ln -sf "$SITE" /etc/nginx/sites-enabled/caravan.conf
  nginx -t
  systemctl reload nginx
}
write_site

if [[ $TLS -eq 1 && ! -f "$CERT" ]]; then
  step "Requesting Let's Encrypt certificate for $DOMAIN"
  if [[ -n "$EMAIL" ]]; then contact=(-m "$EMAIL"); else contact=(--register-unsafely-without-email); fi
  if certbot certonly --webroot -w /var/www/letsencrypt -d "$DOMAIN" \
       --non-interactive --agree-tos "${contact[@]}"; then
    write_site
  else
    echo "!! certbot failed — the site is served over HTTP for now. Check DNS for $DOMAIN points here," >&2
    echo "!! then re-run this script." >&2
  fi
fi
if [[ $TLS -eq 1 ]]; then
  hook=/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
  if [[ -d /etc/letsencrypt && ! -f $hook ]]; then
    install -d "$(dirname "$hook")"
    printf '#!/bin/sh\nsystemctl reload nginx\n' > "$hook"
    chmod 0755 "$hook"
  fi
fi

step "Health check"
ok=0
for _ in $(seq 1 10); do
  if curl -fsS --unix-socket /run/caravan/gunicorn.sock -H "Host: $DOMAIN" \
       -H "X-Forwarded-Proto: https" "http://$DOMAIN/api/static/" -o /dev/null; then
    ok=1; break
  fi
  sleep 1
done
if [[ $ok -eq 1 ]]; then
  echo "app is answering on /run/caravan/gunicorn.sock"
else
  echo "!! app did not answer — see: journalctl -u caravan -n 50" >&2
  exit 1
fi

scheme=$([[ $TLS -eq 1 && -f "$CERT" ]] && echo https || echo http)
printf '\n\033[1;32mDeployed: %s://%s/\033[0m\n' "$scheme" "$DOMAIN"
echo "Logs: journalctl -u caravan -f    Restart: systemctl restart caravan"
