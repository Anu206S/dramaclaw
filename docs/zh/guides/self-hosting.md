<!-- lang-switch -->
[English](../../en/guides/self-hosting.md) · **简体中文**

# 自托管手册（Docker）

> 用 Docker 部署、配置、升级、备份 DramaClaw CE。

CE 默认两个容器：`api` + `web`，**无 PostgreSQL / 无 Redis / 无 Celery**（`ST_EDITION=ce`，任务在进程内 inline 执行）。模型默认走 DramaClaw 官方网关；想纯本地自建网关,用 `docker-compose.selfhosted.yml`(多一个内置 `newapi` 容器)。

## 1. 前置

- Docker + `docker compose`。
- 资源：建议 ≥ 2 vCPU / 4GB（不含模型推理，推理走外部网关）。
- 一个 DC key（默认官方网关 RelayClaw,见 <https://relayclaw.cdnfg.com>），或自己的 OpenAI 兼容网关。

## 2. 拿到 compose 与配置

```bash
git clone https://github.com/dramaclaw/dramaclaw.git
cd dramaclaw
cp .env.example .env
```

`docker-compose.yml` 的关键点（已为你定好，无需改）：

| 项 | 值 | 说明 |
|---|---|---|
| 服务 | `api` + `web` | 无 PG/Redis（自建网关版另起 `newapi`） |
| 端口 | `127.0.0.1:8780:8780` | REST API |
| 强制环境 | `ST_EDITION=ce`、清空 control-plane/Redis/Celery | CE 模式不可降级 |
| 数据卷 | `ce-data:/data`（输出为 `/data/output`） | 持久化项目数据库、设置和生成媒体 |

### 网络访问与升级

CE 没有登录鉴权，能访问服务的客户端就具有本地 owner 权限。所有随项目提供的
Compose 版本默认将 API、Web 和内置网关端口发布到 `127.0.0.1`；修改
`ST_API_PORT`、`ST_WEB_PORT`、`ST_NEWAPI_PORT` 只改变端口号，不改变绑定地址。
API 在**容器内部**仍监听 `0.0.0.0`，以便 Web 容器连接，不要把内部监听也改成回环地址。

个人远程访问可保留默认绑定，通过 `ssh -L 8080:127.0.0.1:8080 user@your-host`
建立隧道后访问本机 8080。若明确要发布共享服务，须在前置代理上配置鉴权，同时
阻止绕过代理直连 API/Web。DC Key 或模型 Key 不是登录保护。检查自定义 Compose
覆盖、Docker 网络/daemon 设置和宿主防火墙；使用受支持的 Docker 版本，28.0.0
之前的版本存在 localhost 端口发布隔离限制。

从旧版全部网卡绑定升级后，原先直接通过 LAN 访问的方式会停止工作。用新版 Compose
重建容器，再通过 `docker compose ps` 或 `docker port` 核对实际绑定；仅重启旧容器
不会修改端口映射。保留数据卷。原生 CE CLI、`scripts/start-ce.sh` 和 Vite 开发代理
也默认绑定回环地址。开发代理连接 CE 时同样暴露 owner 能力，不应直接发布到不可信网络。
CLI 仍可通过显式
`--host`/`NOVELVIDEO_API_HOST` 改写，暴露免登录 owner 时会警告。EE CLI 默认行为不变。
Vite 的 `--host` 和启动脚本的 `SUPERTALE_FE_HOST` 仍支持显式改写前端绑定。

项目文件仍可存储任意内容，正常图片、音视频继续预览。HTML、SVG、脚本格式及未知
后缀改为带 sandbox 的附件下载，存量文件同样受保护；通过 fetch 读取文件字节仍可用。
使用外部媒体缓存的部署升级时，须失效旧的项目文件缓存，或在该代理统一施加新版
sandbox/nosniff 策略。不要移除安全响应头或缓存 `no-store` 响应；独立的对象存储
直出路径需要另行核对。

## 3. 配置 `.env`

> ⚠️ **密钥类默认值（如 `PROMPT_EXPORT_PASSWORD=change_me`）必须改。** 模型网关见 [模型配置](#模型配置)。

分组（`.env.example` 内有逐项注释）：本地 NewAPI provisioner、参考媒体 OSS relay（OSS_RELAY_*）、Cognee 知识图谱、文本/图片/视频/音频各模型、图像与视频基础参数、UI、输出目录。渠道、网关地址和 token 通过网页保存到 `settings.db`。

### 模型配置

推荐与备选(详见 [配置模型供应商](../getting-started/configuring-models.md)):

- **A. DC 官方 key(推荐)**：默认 compose 已走官方网关。起栈后开 `http://localhost:8080` → 设置 → 模型配置 → 官方渠道 → 粘贴 DC key 保存即用,**无需映射模型**。到 <https://relayclaw.cdnfg.com> 取 key。
- **B. 本地 NewAPI**：改用 `docker compose -f docker-compose.selfhosted.yml up`，然后在网页「本地 NewAPI」页初始化并配置上游渠道和模型映射。

本地 NewAPI 需把 DramaClaw 逻辑模型映射到真实上游模型。参考图功能需要 `OSS_RELAY_AK/SK`（纯文本流程可暂不配）。

## 4. 起停

```bash
docker compose up -d --build     # 启动（首次构建）
docker compose ps                # 状态
docker compose logs -f api       # 日志
docker compose down              # 停止（保留数据卷）
```

## 5. 数据在哪 / 备份、恢复与迁移

- 项目数据库、设置和生成媒体都在命名卷 `ce-data`（容器内 `/data`）；生成媒体固定写入 `/data/output`。删除或重建容器不会删除该卷，只有显式执行 `docker compose down -v` 才会删除。
- 备份数据卷：

```bash
docker run --rm -v dramaclaw-ce_ce-data:/data -v "$PWD":/backup alpine \
  tar czf /backup/ce-data-backup.tar.gz -C /data .
```

（卷名前缀随 compose 项目名，`docker volume ls` 确认实际名。）

- 恢复 / 搬到新机 —— 把 `ce-data-backup.tar.gz` 拷到目标机，反向解回数据卷（`-v` 挂载会在卷不存在时自动创建）：

```bash
docker run --rm -v dramaclaw-ce_ce-data:/data -v "$PWD":/backup alpine \
  tar xzf /backup/ce-data-backup.tar.gz -C /data
```

然后照常起服务（`docker compose -f docker-compose.selfhosted.yml up -d`）。数据卷备份已包含生成媒体；`.env` 仍需单独备份。

## 6. 升级

> 🚧 当前由源码构建，升级 = 拉新代码后重建：

```bash
git pull
docker compose up -d --build
```

如果旧版本曾将媒体写入容器内 `/app/output`，请在重建旧容器**之前**运行一次迁移：

```bash
git pull
docker compose exec -T api python - < scripts/migrate_docker_output.py
docker compose up -d --build
```

Windows PowerShell 使用：

```powershell
git pull
Get-Content scripts/migrate_docker_output.py -Raw | docker compose exec -T api python -
docker compose up -d --build
```

脚本只补拷缺失文件，不覆盖或删除源文件；修改项目前会备份 `projects.db`。如果旧容器已经被删除，原本仅存在于该容器层的文件无法由数据卷恢复。

正式发布后改为**拉取钉版本的已发布镜像** + env-sync（升级保留你的自定义 `.env` 值）——见发行规格落地后更新本节。

## 7. 排错

| 现象 | 排查 |
|---|---|
| 容器起不来 | `docker compose logs api`；多半是 `.env` 网关地址/Key 未改或不可达 |
| 8780 端口占用 | 改 compose `ports` 左值，如 `127.0.0.1:8888:8780` |
| 模型调用报错 | 确认网关可达、`*_MODEL` 名在网关后台存在 |

## 相关

- [快速开始](../getting-started/quickstart.md) ｜ [配置模型供应商](../getting-started/configuring-models.md)
