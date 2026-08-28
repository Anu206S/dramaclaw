<!-- lang-switch -->
**English** · [简体中文](../../zh/guides/self-hosting.md)

# Self-Hosting Handbook (Docker)

> Deploy, configure, upgrade, and back up DramaClaw CE with Docker.

CE ships two containers by default: `api` + `web`, with **no PostgreSQL / no Redis / no Celery** (`ST_EDITION=ce`; tasks run inline within the process). Models go through the official DramaClaw gateway by default. If you want a purely local, self-hosted gateway, use `docker-compose.selfhosted.yml` (which adds a bundled `newapi` container).

## 1. Prerequisites

- Docker + `docker compose`.
- Resources: ≥ 2 vCPU / 4GB recommended (excluding model inference, which runs through an external gateway).
- A DC key (the default official gateway is RelayClaw, see <https://relayclaw.cdnfg.com>), or your own OpenAI-compatible gateway.

## 2. Get the compose files and configuration

```bash
git clone https://github.com/dramaclaw/dramaclaw.git
cd dramaclaw
cp .env.example .env
```

Key points in `docker-compose.yml` (already set for you, no changes needed):

| Item | Value | Notes |
|---|---|---|
| Services | `api` + `web` | No PG/Redis (the self-hosted-gateway variant adds `newapi`) |
| Port | `127.0.0.1:8780:8780` | REST API |
| Enforced environment | `ST_EDITION=ce`, control-plane/Redis/Celery cleared | CE mode cannot be downgraded |
| Data volume | `ce-data:/data` (output at `/data/output`) | Persists project databases, settings, and generated media |

### Network access and upgrades

CE has no login: any client that can reach it has local owner authority. All
shipped Compose variants publish the API, web, and bundled gateway ports on
`127.0.0.1` by default. Changing `ST_API_PORT`, `ST_WEB_PORT`, or
`ST_NEWAPI_PORT` changes only the port number, not this protection. The API
still listens on `0.0.0.0` **inside** its container so the web container can
reach it; do not change that internal listener to loopback.

For personal remote access, keep these bindings and use an SSH tunnel, e.g.
`ssh -L 8080:127.0.0.1:8080 user@your-host`, then open local port 8080. If you
deliberately publish a shared service, place authentication in front of it and
block direct access to both the API and web ports. A DC/model key is not login
protection. Review custom Compose overrides, daemon/network routing settings,
and host firewall rules; use a supported Docker release (versions before 28.0.0
have known localhost-publishing isolation limitations).

An upgrade from all-interface publication stops implicit LAN access. Recreate
containers with the updated Compose files and inspect `docker compose ps` or
`docker port` to verify the effective bindings; restarting an old container does
not change its port mappings. Preserve the data volume. The native CE CLI,
`scripts/start-ce.sh`, and the Vite development proxy also default to loopback.
A development proxy connected to CE exposes owner capabilities too; do not
publish it directly to an untrusted network. An explicit CLI
`--host`/`NOVELVIDEO_API_HOST` override remains available and warns when it exposes
no-login owner access. EE CLI defaults are unchanged. Vite's `--host` and the
launcher's `SUPERTALE_FE_HOST` still allow deliberate frontend bind overrides.

Project file delivery preserves normal image/audio/video previews and arbitrary
file storage. HTML, SVG, script formats, and unknown extensions are served as
sandboxed attachments, including existing files; fetching file bytes still works.
When upgrading a deployment with an external media cache, invalidate previously
cached project-file responses or enforce the new sandbox/nosniff response policy
at that proxy. Do not let a custom proxy remove those headers or cache responses
marked `no-store`. Review any direct object-storage delivery paths separately.

## 3. Configure `.env`

> ⚠️ **Secret-type defaults (such as `PROMPT_EXPORT_PASSWORD=change_me`) must be changed.** For the model gateway, see [Model Configuration](#model-configuration).

Groups (each item is commented inline in `.env.example`): local NewAPI provisioner, reference-media OSS relay (OSS_RELAY_*), Cognee knowledge graph, text/image/video/audio models, image and video base parameters, UI, and output directories. Channel selection, gateway address, and token are saved from the web UI to `settings.db`.

### Model Configuration

Recommended and alternative options (see [Configuring Model Providers](../getting-started/configuring-models.md) for details):

- **A. DC official key (recommended)**: the default compose already uses the official gateway. After bringing the stack up, open `http://localhost:8080` → Settings → Model Configuration → Official Channel → paste your DC key and save to start using it, **no model mapping required**. Get a key at <https://relayclaw.cdnfg.com>.
- **B. Local NewAPI**: switch to `docker compose -f docker-compose.selfhosted.yml up`, then initialize it and configure upstream channels and model mappings from the Local NewAPI page.

Local NewAPI must map DramaClaw's logical models to real upstream models. The reference-image feature needs `OSS_RELAY_AK/SK` (you can skip it for a text-only workflow).

## 4. Start / Stop

```bash
docker compose up -d --build     # start (builds on first run)
docker compose ps                # status
docker compose logs -f api       # logs
docker compose down              # stop (keeps the data volume)
```

## 5. Where the data lives / Backup, restore & migrate

- Project databases, settings, and generated media live in the named volume `ce-data` (`/data` inside the container); generated media is written to `/data/output`. Removing or rebuilding a container keeps this volume. Only an explicit `docker compose down -v` removes it.
- Back up the data volume:

```bash
docker run --rm -v dramaclaw-ce_ce-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/ce-data-backup.tar.gz -C /data .
```

(The volume name is prefixed with the compose project name; run `docker volume ls` to confirm the actual name.)

- Restore, or move to a new machine — copy `ce-data-backup.tar.gz` to the target host, then unpack it back into the data volume (the `-v` mount creates the volume if it does not exist yet):

```bash
docker run --rm -v dramaclaw-ce_ce-data:/data -v "$PWD":/backup alpine \
  tar xzf /backup/ce-data-backup.tar.gz -C /data
```

Then bring the stack up as usual (`docker compose -f docker-compose.selfhosted.yml up -d`). The volume backup already includes generated media; back up `.env` separately.

## 6. Upgrades

> 🚧 Currently built from source, so upgrading = pull the new code and rebuild:

```bash
git pull
docker compose up -d --build
```

If an older release wrote media to `/app/output` inside the container, run the one-time migration **before** rebuilding that old container:

```bash
git pull
docker compose exec -T api python - < scripts/migrate_docker_output.py
docker compose up -d --build
```

On Windows PowerShell:

```powershell
git pull
Get-Content scripts/migrate_docker_output.py -Raw | docker compose exec -T api python -
docker compose up -d --build
```

The script copies only missing files, never overwrites or deletes the source, and backs up `projects.db` before updating project paths. Files that existed only in an already-removed container layer cannot be recovered from the data volume.

After the formal release this will switch to **pulling published, pinned-version images** + env-sync (upgrades preserve your custom `.env` values) — this section will be updated once the release spec lands.

## 7. Troubleshooting

| Symptom | What to check |
|---|---|
| Container won't start | `docker compose logs api`; usually the `.env` gateway address/key was not changed or is unreachable |
| Port 8780 already in use | Change the left-hand value of `ports` in compose, e.g. `127.0.0.1:8888:8780` |
| Model call errors | Confirm the gateway is reachable and that the `*_MODEL` names exist in the gateway backend |

## Related

- [Quickstart](../getting-started/quickstart.md) ｜ [Configuring Model Providers](../getting-started/configuring-models.md)
