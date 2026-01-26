<div align="center">
  <img src="./images/logo.svg" width="360" alt="php-nginx-docker logo" />

# WordPress + Nginx + PHP-FPM Docker Template

**Battle-tested WordPress images layered on top of the secured php-nginx stack.**

[![CI/CD](https://github.com/nooblk-98/wordpress-docker-template/actions/workflows/build-and-push.yml/badge.svg)](https://github.com/nooblk-98/wordpress-docker-template/actions/workflows/build-and-push.yml)
[![PHP Version](https://img.shields.io/badge/PHP-7.4%20|%208.1%20|%208.2%20|%208.3%20|%208.4-777BB4?logo=php&logoColor=white)](https://www.php.net/)
[![Wordpress](https://img.shields.io/badge/wordpress-latest-21759B?logo=wordpress&logoColor=white)](https://wordpress.org/)
[![Nginx](https://img.shields.io/badge/Nginx-Latest-009639?logo=nginx&logoColor=white)](https://nginx.org/)
[![Docker](https://img.shields.io/badge/Docker-20.10+-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: AGPL](https://img.shields.io/badge/license-AGPL--3.0-blue.svg)](http://www.gnu.org/licenses/agpl-3.0)
[![Last Commit](https://img.shields.io/github/last-commit/nooblk-98/wordpress-docker-template)](https://github.com/nooblk-98/wordpress-docker-template/commits/main)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](https://github.com/nooblk-98/wordpress-docker-template/blob/main/CONTRIBUTING.md)

[Docker Hub Repository](https://hub.docker.com/repository/docker/lahiru98s/wordpress)

</div>

---

### What is included

- WordPress core downloaded at build time (override with `WORDPRESS_VERSION`).
- WP-CLI installed globally and used to generate `wp-config.php` with sane defaults.
- Nginx + PHP-FPM tuned for WordPress, served by a non-root `app` user.
- Supervisor as process manager with Tini for proper signal handling.
- Health endpoints (`/fpm-ping`, `/fpm-status`) and Docker healthcheck.

---

## Features

### Security and hardening
- Non-root `app` user, locked-down Nginx headers, and minimal Alpine base inherited from the php-nginx image.
- Salts shuffled on first boot; config generation avoids exposing secrets in images.
- Socket-based PHP-FPM and supervisor-managed processes for predictable restarts.

### WordPress experience
- `wp-config.php` auto-created if missing; respects DB/env overrides and common toggles (debug, cache, cron, SSL admin, environment type).
- Optional automatic `wp core install` when the database is reachable (`WORDPRESS_AUTO_INSTALL=true`).
- Sensible PHP overrides for file uploads, memory/time limits, and input vars via [php/php.ini](php/php.ini).

### Operations and observability
- Health endpoints wired to the Docker healthcheck in [Dockerfile](Dockerfile).
- Structured logging through Nginx and PHP-FPM; Supervisor keeps services up.
- One-command compose stack with MariaDB and persistent volumes.

### Flexibility
- Build or pull per-PHP version tags (7.4, 8.1, 8.2, 8.3, 8.4) mirroring the base image layout.
- Override WordPress version, PHP tag, and PHP package version through build args.
- Drop-in config overrides for Nginx, PHP-FPM, and Supervisor.

---

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
services:
  wordpress:
    image: lahiru98s/wordpress:latest
    ports:
      - "8080:8080"
    environment:
      WORDPRESS_DB_HOST: db:3306
      WORDPRESS_DB_NAME: wordpress
      WORDPRESS_DB_USER: wordpress
      WORDPRESS_DB_PASSWORD: wordpress
      WORDPRESS_AUTO_INSTALL: "true"
      WORDPRESS_SITE_URL: http://localhost:8080
      WORDPRESS_SITE_TITLE: "WordPress on Nginx"
      WORDPRESS_ADMIN_USER: admin
      WORDPRESS_ADMIN_PASSWORD: admin
      WORDPRESS_ADMIN_EMAIL: admin@example.com
    volumes:
      - wp_data:/var/www/html/wp-content
    depends_on:
      - db

  db:
    image: mariadb:11
    restart: unless-stopped
    environment:
      MYSQL_DATABASE: wordpress
      MYSQL_USER: wordpress
      MYSQL_PASSWORD: wordpress
      MYSQL_ROOT_PASSWORD: rootpassword
    volumes:
      - db_data:/var/lib/mysql

volumes:
  db_data:
  wp_data:
```



```bash
# permissions for files
chown -R www-data:www-data /var/www/html
```

```bash
docker compose up -d
```
```bash
open http://localhost:8080
```

`docker-compose.yml` builds the PHP 8.4 image by default, starts MariaDB 11, and enables automatic WordPress installation with starter admin credentials. Uncomment the provided volume lines to persist uploads and database data.

### Option 2: Run with an external database

```bash
docker run -d \
  --name wordpress-nginx \
  -p 8080:8080 \
  -e WORDPRESS_DB_HOST=your-db:3306 \
  -e WORDPRESS_DB_USER=wordpress \
  -e WORDPRESS_DB_PASSWORD=wordpress \
  lahiru98s/wordpress-nginx:8.4
```

### Option 3: Pull image directly

```bash
docker pull lahiru98s/wordpress-nginx:8.4
```

---

## Available tags

| PHP version | Image tag | Dockerfile | Status |
| ----------- | --------- | ---------- | ------ |
| 8.4 | `8.4`, `latest` | [wp84/Dockerfile](wp84/Dockerfile) | Stable |
| 8.3 | `8.3` | [wp83/Dockerfile](wp83/Dockerfile) | Stable |
| 8.2 | `8.2` | [wp82/Dockerfile](wp82/Dockerfile) | Stable |
| 8.1 | `8.1` | [wp81/Dockerfile](wp81/Dockerfile) | Stable |
| 7.4 | `7.4` | [wp74/Dockerfile](wp74/Dockerfile) | Legacy |

Default build args: `PHP_TAG=8.4`, `PHP_VERSION=84`, `WORDPRESS_VERSION=latest`.

---

## Building from source

### Generic build (default PHP 8.4)

```bash
docker build -t lahiru98s/wordpress-nginx:8.4 .
```

### Pin PHP/WordPress versions

```bash
docker build \
  -t lahiru98s/wordpress-nginx:8.3 \
  --build-arg PHP_TAG=8.3 \
  --build-arg PHP_VERSION=83 \
  --build-arg WORDPRESS_VERSION=6.7.1 \
  .
```

### Build from a versioned Dockerfile

```bash
docker build -t lahiru98s/wordpress-nginx:8.1 -f wp81/Dockerfile .
```

---

## Configuration

Entrypoint environment variables (all optional):

- `WORDPRESS_DB_HOST` (default `db:3306`)
- `WORDPRESS_DB_NAME` (default `wordpress`)
- `WORDPRESS_DB_USER` and `WORDPRESS_DB_PASSWORD` (default `wordpress`/`wordpress`)
- `WORDPRESS_TABLE_PREFIX` (default `wp_`)
- `WORDPRESS_DEBUG`, `WORDPRESS_CACHE`, `WORDPRESS_FORCE_SSL_ADMIN`, `WORDPRESS_DISABLE_CRON`, `WORDPRESS_ENVIRONMENT_TYPE` (defaults: `false`, `false`, `false`, `false`, `production`)
- `WORDPRESS_AUTO_INSTALL` (`true` triggers `wp core install` once DB is reachable)
- `WORDPRESS_SITE_URL`, `WORDPRESS_SITE_TITLE`, `WORDPRESS_ADMIN_USER`, `WORDPRESS_ADMIN_PASSWORD`, `WORDPRESS_ADMIN_EMAIL` (used only when auto-install is enabled)
- `WORDPRESS_PATH` (default `/var/www/html`)

Volume examples:

```yaml
services:
  wordpress:
    volumes:
      - ./wp-data:/var/www/html/wp-content
  db:
    volumes:
      - ./db-data:/var/lib/mysql
```

Key configuration files:

- [nginx/nginx.conf](nginx/nginx.conf) and [nginx/conf.d/default.conf](nginx/conf.d/default.conf)
- [php/php.ini](php/php.ini)
- [supervisord/supervisord.conf](supervisord/supervisord.conf)
- [docker/entrypoint.sh](docker/entrypoint.sh)

---

## Monitoring and health

- FPM ping: `http://localhost:8080/fpm-ping`
- FPM status: `http://localhost:8080/fpm-status`
- Docker health status: `docker inspect --format='{{.State.Health.Status}}' wordpress` (container name may differ)

Log examples:

```bash
docker compose logs -f
docker logs wordpress
docker exec wordpress tail -f /var/log/nginx/access.log
docker exec wordpress tail -f /var/log/php-fpm/error.log
```

---

## Troubleshooting

- `apk add php81-* not found`: build with the matching Alpine release by picking the versioned Dockerfile or overriding `PHP_TAG`/`PHP_VERSION` consistently.
- Healthcheck failing: verify the FPM socket exists (`/run/php/php-fpm.sock`) and that Nginx config validates (`nginx -t`).
- Permission denied on mounts: ensure mounted paths are writable by UID/GID 1000 (`app` user) or set `user: "1000:1000"` in compose.
- White page: enable temporary error display (`display_errors = On` in PHP overrides) and check PHP-FPM logs.

---

## Contributing

1) Fork and create a feature branch. 2) Make changes with tests or manual checks across supported PHP versions. 3) Update documentation when behavior changes. 4) Open a PR with a clear summary.

---

## 📝 License

This project is licensed under the **GNU Affero General Public License v3.0** (AGPL-3.0).
See [LICENSE](LICENSE) for full details.


---

<div align="center">

**Made with ❤️ by NoobLK**

[⬆ Back to top](#wordpress-docker-template)

</div>
