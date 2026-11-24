# Deploying Caravan Road

Target: a Debian (12/13+) server that already runs other things behind nginx.
The app runs as gunicorn under its own system user `caravan` and serves `caravan.whydidweevendothis.com`.

## First install

1. Point DNS for `caravan.whydidweevendothis.com` at the server.
2. Make sure ports 80 and 443 reach nginx.
3. Then run:

```bash
git clone <your-remote> ~/caravan        # any location; it is only the source
cd ~/caravan
sudo ./deploy/deploy.sh --email you@example.com
```

## Updates

```bash
cd ~/caravan && git pull && sudo ./deploy/deploy.sh
```

The script is idempotent, so you can re-run it as often as you like. Each run:

- **Packages:** installs any missing ones (`python3-venv nginx rsync sqlite3 curl certbot`).
- **User and folders:** creates the `caravan` system user (no login shell) and `/srv/caravan`.
- **Code:** copies the code into `/srv/caravan/app` with `rsync --delete`, so the live app never runs from your checkout. Everything ends up owned by `caravan`.
- **Python:** builds or updates the virtualenv `/srv/caravan/venv` from `requirements.txt`.
- **Settings file:** on the first run only, writes `/etc/caravan/caravan.env` (`root:caravan 0640`) with a freshly generated secret key. Later runs never overwrite it.
- **Django:** runs `migrate`, `collectstatic` into `/srv/caravan/static`, and `check --deploy`.
- **systemd:** installs the units and restarts the app:
  - `caravan.socket` and `caravan.service`
  - `caravan-cleanup.timer`, which deletes stale games daily
- **nginx:** writes its own vhost, `/etc/nginx/sites-available/caravan.conf`, plus `/etc/nginx/snippets/caravan-app.conf`. It runs `nginx -t` and reloads nginx. It never touches other sites.
- **TLS:** on the first run, gets a Let's Encrypt certificate using `certbot certonly --webroot`. Certbot never edits the nginx config, so later runs can safely rewrite the vhost. It also adds a renewal hook that reloads nginx.
- **Health check:** finishes by checking that the app answers on its socket.

Options:

| Flag | Effect |
| --- | --- |
| `--domain example.org` | Serve a different domain. You can also set `CARAVAN_DOMAIN=…`. |
| `--email you@x` | Contact address for Let's Encrypt. |
| `--no-tls` | HTTP only, e.g. if TLS ends at a load balancer or Cloudflare. |
| `--skip-apt` | Don't touch system packages. |

## Layout on the server

```
/srv/caravan/            caravan:caravan 0751
  app/                   code (rsynced copy)       0750
  venv/                  virtualenv                0750
  data/db.sqlite3        game database (WAL mode)  0750
  static/                collected static, served directly by nginx
/etc/caravan/caravan.env secrets/config            root:caravan 0640
/run/caravan/gunicorn.sock  owned by www-data (systemd socket activation)
```

nginx talks to gunicorn over a unix socket. systemd owns the socket and hands it to gunicorn, so:

- nginx (`www-data`) can connect to it.
- The app process itself stays unprivileged and sandboxed. `ProtectSystem=strict` is set, and the database folder is its only writable path.
- During restarts, requests wait in the socket queue instead of failing.

SQLite runs in WAL mode with `IMMEDIATE` transactions. That keeps game actions consistent across the gunicorn workers and is plenty for a turn-based game. To back up the database:

```bash
sudo -u caravan sqlite3 /srv/caravan/data/db.sqlite3 ".backup '/srv/caravan/data/backup.sqlite3'"
```

## Operating

```bash
journalctl -u caravan -f                      # app logs
systemctl restart caravan                     # restart (zero-drop thanks to the socket)
systemctl list-timers caravan-cleanup.timer   # cleanup schedule
sudo -u caravan bash -c 'set -a; . /etc/caravan/caravan.env; cd /srv/caravan/app; \
  /srv/caravan/venv/bin/python manage.py createsuperuser'   # admin at /admin/
```

## Uninstall

```bash
sudo systemctl disable --now caravan.service caravan.socket caravan-cleanup.timer
sudo rm /etc/systemd/system/caravan* /etc/nginx/sites-enabled/caravan.conf \
        /etc/nginx/sites-available/caravan.conf /etc/nginx/snippets/caravan-app.conf
sudo systemctl daemon-reload && sudo systemctl reload nginx
sudo rm -rf /srv/caravan /etc/caravan && sudo deluser --system caravan
```
