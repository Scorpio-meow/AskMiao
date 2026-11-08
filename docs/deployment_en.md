# Deployment Guide

[繁體中文](deployment.md) | [English](deployment_en.md)

> Run AskMiao on one host (for example a VM) with the Docker Compose setup in `deploy/`: three containers for PostgreSQL, the backend, and nginx serving the frontend. To develop or try it on your own computer, see [README: Quick Start](../README_en.md#quick-start); every setting is described in the [configuration reference](configuration_en.md).

## Contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [Deployment steps](#deployment-steps)
- [Serving over HTTPS](#serving-over-https)
- [Data and backups](#data-and-backups)
- [Updating to a new release](#updating-to-a-new-release)
- [Common commands](#common-commands)

## Architecture

| Service | Image | Role |
|---|---|---|
| `postgres` | `postgres:17.9` | The `chatbot` database. When the volume is first initialized it runs `backend/init.sql` (creates the tables) and then `backend/init-app-role.sh` (creates the non-superuser `POSTGRES_APP_USER` the backend connects as). No port is published to the host |
| `backend` | `deploy/Dockerfile.backend` (`python:3.12-slim` with the CPU build of PyTorch and `tzdata`) | The FastAPI backend, running as the `askmiao` account (uid 1000) in the `Asia/Taipei` time zone, which the research assistant uses to tell the current date and time. It starts after the `postgres` health check passes; the first start downloads the embedding and reranker models, so its health check (`GET /health`) allows 180 seconds before failures count |
| `web` | `deploy/Dockerfile.frontend` (built with `oven/bun:1`, served by `nginx:1.27-alpine`) | Serves the frontend build and reverse-proxies `/api/` to `backend:8001`. The only service published to the host, on `WEB_PORT` |

The time zone of `postgres` and `backend` comes from `TZ` in `deploy/docker-compose.yml`; if your users are in another time zone, change both to the local IANA time zone name.

The three containers share the compose network `askmiao-net` (subnet `NETWORK_SUBNET`), and `web` always uses `WEB_CONTAINER_IP`. nginx accepts request bodies up to 120 MiB, does not buffer SSE streams, and uses 900-second read and send timeouts (`deploy/nginx.conf`).

## Requirements

- Docker Engine with Compose v2 (the `docker compose` command).
- bash and openssl to run `deploy/gen-env.sh`.
- The first start downloads about 1.2 GB of models into the `backend_data` volume, so the host must reach Hugging Face.
- Model endpoints and keys are not in the configuration file; they are set up as API connections in the UI after startup (step 5 of [Deployment steps](#deployment-steps)).

## Deployment steps

### 1. Get the source

```bash
git clone https://github.com/Scorpio-meow/AskMiao.git
cd AskMiao/deploy
```

### 2. Generate `deploy/.env`

```bash
PUBLIC_ORIGIN=https://askmiao.example.com \
WEB_PORT=8080 \
NETWORK_SUBNET=172.31.240.0/24 \
WEB_CONTAINER_IP=172.31.240.10 \
./gen-env.sh
```

| Variable | Description |
|---|---|
| `PUBLIC_ORIGIN` | The origin (scheme, host, and port) users open AskMiao at in the browser. Written to `ALLOWED_ORIGINS`; when it starts with `https://`, `COOKIE_SECURE` is set to `true` |
| `WEB_PORT` | The host port mapped to port 80 of the `web` container |
| `NETWORK_SUBNET` | The subnet of the compose network. Pick a range that does not overlap the company network, a VPN, or other Docker networks on the host |
| `WEB_CONTAINER_IP` | The fixed IP of the `web` container inside that subnet, written to `FORWARDED_ALLOW_IPS` so the backend trusts the `X-Forwarded-For` header nginx sends |

`gen-env.sh` copies `backend/.env.example` and appends the deployment settings: `HOST=0.0.0.0`, `ENVIRONMENT=production`, `COOKIE_SECURE`, a randomly generated `TOOL_SECRETS_KEY`, `POSTGRES_PASSWORD` and `POSTGRES_APP_PASSWORD`, `POSTGRES_APP_USER=askmiao_app`, a `DATABASE_URL` pointing at `postgres:5432`, and the four values above. Only the owner can read or write the file, and the script refuses to overwrite an existing `deploy/.env`.

The file is both the source of compose variables and the environment of the backend container. Other settings (for example `MAX_FILE_SIZE_MB` or `ALLOW_REGISTRATION`) can be edited directly in `deploy/.env`; see the [configuration reference](configuration_en.md) for each one.

> [!IMPORTANT]
> Keep `deploy/.env` safe and separate from the database backups. If `TOOL_SECRETS_KEY` is lost or replaced, stored custom API tool credentials, MCP server credentials, and API connection keys can no longer be decrypted and must be entered again.

### 3. Build and start

```bash
docker compose up -d --build
```

`web` waits until the `backend` health check passes. Downloading the models on the first start takes a few minutes; follow the progress with `docker compose logs -f backend`.

### 4. Create the first admin

```bash
docker compose exec backend python scripts/create_user.py --username admin --email admin@example.com --admin
```

Enter the password twice when prompted. The template's `ALLOW_REGISTRATION=false` disables self-registration; create other accounts with the same command (leave out `--admin` for a regular user), or have an admin add them on the Admin page.

### 5. Set up models and upload documents

Open `PUBLIC_ORIGIN` in the browser and sign in as the admin. Create a connection under "Admin → Shared API connections", then upload documents on the knowledge base page; the steps are the same as in [README: Upload documents and ask](../README_en.md#5-upload-documents-and-ask).

## Serving over HTTPS

The `web` container serves plain HTTP. To serve AskMiao over HTTPS, terminate TLS on the host or in a reverse proxy in front of it and forward to `WEB_PORT`:

- Set `PUBLIC_ORIGIN` to the `https://` address users actually open, so the refresh-token cookie is marked `Secure`.
- The reverse proxy in front must accept the same 120 MiB request bodies as the nginx in the container, must not buffer SSE responses, and needs a read timeout of at least 900 seconds, or long research runs are cut off.
- The nginx in the container forwards `X-Forwarded-For: $remote_addr`. With another reverse proxy in front, the backend sees that proxy as the client address for everyone, so the rate limit and per-address login throttling are shared by all users. See [configuration reference: login throttling](configuration_en.md#login-throttling) when choosing the thresholds.

## Data and backups

| Volume | Path in the container | Contents |
|---|---|---|
| `postgres_data` | `/var/lib/postgresql/data` | Users, conversations, documents and chunks (`rag_chunks`), tools, skills, and API connections |
| `backend_data` | `/app/data` | Uploaded originals, the FAISS and BM25 indexes, Agent Skills files (`SKILLS_DIR`), and the model cache |
| `backend_keys` | `/app/keys` | The RSA keys that sign JWTs. If they are lost, everyone has to sign in again |
| `backend_logs` | `/app/logs` | `app.log` and `security.log` |

Back up together:

1. The database: `docker compose exec postgres pg_dump -U postgres chatbot > askmiao.sql`.
2. `deploy/.env` (it holds `TOOL_SECRETS_KEY` and the database passwords).
3. The uploaded files and skill files in `backend_data`. The FAISS and BM25 indexes need no backup: at startup the backend fills in missing indexes from `rag_chunks` in the database (see [architecture: reconciliation at startup](architecture_en.md#reconciliation-at-startup)), and the model cache can be downloaded again.

`docker compose down` keeps the volumes; `docker compose down -v` deletes them along with all data.

## Updating to a new release

1. Read every section of the [upgrade guide](upgrading_en.md) from your current release to the new one, and back up your data.
2. After updating the source, rebuild and start from `deploy/`:

   ```bash
   docker compose up -d --build
   ```

3. Add any required settings introduced by the new release to `deploy/.env` by hand (`gen-env.sh` does not overwrite an existing file), for example `LOG_DIR` from 8.0.0. Without them the backend does not start, and `docker compose logs backend` names the missing fields.

New table columns are added automatically when the backend starts; no separate migration step is needed.

## Common commands

Run from `deploy/`:

| Command | Purpose |
|---|---|
| `docker compose ps` | Status and health check results of the three services |
| `docker compose logs -f backend` | Follow the backend log |
| `docker compose up -d` | Apply changes to `deploy/.env` by recreating the containers whose configuration changed (`restart` does not reread `deploy/.env`) |
| `docker compose exec backend python scripts/<script>` | Run a maintenance script; see [README: Maintenance scripts](../README_en.md#maintenance-scripts) |
| `docker compose down` | Stop and remove the containers, keeping the volumes |