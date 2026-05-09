# Docker Compose + 宿主机 Nginx + ESA/CDN 部署指南

本文面向以下真实部署拓扑：

- 源站服务器：阿里云 ECS，Ubuntu Server；数据盘挂载到宿主机 `/data`。
- 应用部署：Docker Compose 启动 new-api、Argus、PostgreSQL、Redis。
- 反向代理：宿主机 Nginx 监听 80/443，分别反代到本机 `127.0.0.1:3000` 和 `127.0.0.1:8000`。
- 源站域名：`1tok-origin.xhh.club`，解析到 ECS 公网 IP，只给阿里云 ESA 回源使用。
- 公开域名：`1tok.xhh.club`，当前已接阿里云 ESA。
- Argus 测试域名：`ct.xhh.club`，先直连源站 Nginx 做预发布测试。
- Argus 公开域名：`cheaptoken.io` 和 `www.cheaptoken.io`，正式对外走 Cloudflare CDN/边缘服务。
- 边缘层：`1tok.xhh.club` 使用阿里云 ESA；`cheaptoken.io` 使用 Cloudflare。两者都只缓存静态资源，动态请求必须回源。

这套结构和你以前熟悉的 `uWSGI + Nginx` 很像：区别只是应用进程不再由宿主机直接启动，而是由 Docker Compose 管理。宿主机 Nginx 仍然负责 TLS、反代、WebSocket/SSE 透传、源站保护和统一日志；阿里云 ESA 与 Cloudflare 负责边缘加速、缓存规则、回源策略和安全规则。

## 1. 部署判断

建议使用“宿主机 Nginx + Docker Compose 应用栈”，原因如下：

- Nginx 放宿主机，证书、80/443 端口、防火墙、ESA/CDN 回源规则都更直观。
- Compose 内部只暴露 `127.0.0.1:3000` 和 `127.0.0.1:8000`，PostgreSQL 和 Redis 不暴露公网。
- 以后从单机升级到 RDS/独立 Redis/多节点时，不需要改变用户访问入口。
- 这个项目有流式响应和 WebSocket 路由，Nginx 可以集中关闭代理缓冲并拉长超时。

数据库建议先用 Compose 内的 PostgreSQL。SQLite 只适合试用；MySQL 也支持，但这个项目需要同时兼容多数据库，PostgreSQL 在生产里更稳妥。Argus 与 1tok 共用同一个 PostgreSQL 实例，但使用独立 database `argus`；Redis 共用同一个实例，但使用 Redis DB 2 和 `argus` key prefix。如果后续用户量、账单流水或可靠性要求上来，再迁到阿里云 RDS PostgreSQL 和独立 Redis。

## 2. 项目路由与 ESA/CDN 缓存边界

根据当前代码路由，ESA/CDN 不能简单“全站缓存”。应该理解为“全站经过边缘网络”，但只缓存静态资源。

必须回源且不缓存的路径：

| 路径 | 用途 | ESA 策略 |
| --- | --- | --- |
| `/api/*` | 登录、管理后台、用户、渠道、支付回调、状态等 | 不缓存，回源 |
| `/v1/*` | OpenAI/Claude 兼容 API、视频 API、`/v1/realtime` WebSocket | 不缓存，回源，支持流式/WebSocket |
| `/v1beta/*` | Gemini 兼容 API | 不缓存，回源 |
| `/mj/*`、`/:mode/mj/*` | Midjourney API 与图片代理 | 不缓存，回源 |
| `/suno/*` | Suno 任务 API | 不缓存，回源 |
| `/kling/v1/*` | Kling 视频 API | 不缓存，回源 |
| `/jimeng/*` | 即梦视频 API | 不缓存，回源 |
| `/pg/*` | Playground API | 不缓存，回源 |
| `/dashboard/*`、`/v1/dashboard/*` | 兼容旧 dashboard billing API | 不缓存，回源 |
| `/`、无扩展 SPA 路径 | React 入口和前端路由 fallback | 不缓存或遵循源站 `no-cache` |

Argus / CheapToken 域名必须回源且不缓存的路径：

| 路径 | 用途 | Cloudflare 策略 |
| --- | --- | --- |
| `/`、`/index.html`、`/preview-site/` | 首页、匿名站点预览、表单提交 | 动态 HTML 不缓存，表单 POST 直接回源 |
| `/account/*`、`/auth/*` | 登录页、验证码发送与验证、退出登录 | 不缓存，允许 POST 回源 |
| `/watchlist/*`、`/comparison/*` | 登录后的监测站点、比价、规则和采集操作 | 不缓存，允许 POST 回源 |
| `/pricing/*` | 套餐页、下单、易支付 notify/return | 不缓存，允许 POST 回源 |
| `/admin/*` | Django Admin | 不缓存，建议只给管理员访问 |

可以缓存的路径：

| 路径 | 用途 | 建议 TTL |
| --- | --- | --- |
| `/assets/*` | Vite 构建产物，通常带 hash | 7 天到 30 天 |
| `/favicon.ico`、`/logo_1tok.jpg`、`/logo_xhh.png`、`/robots.txt` | public 静态文件 | 1 天到 7 天 |
| `/cover-4.webp`、`/ratio.png`、`/azure_model_name.png`、`/pay-*.png` | public 图片 | 1 天到 7 天 |

Argus / CheapToken 可以缓存的路径：

| 路径 | 用途 | 建议 TTL |
| --- | --- | --- |
| `/static/*` | Django collectstatic 产物，WhiteNoise 可返回压缩文件 | 7 天到 30 天 |
| `/favicon.ico` | CheapToken favicon | 1 天到 7 天 |

项目自己的 Web 缓存中间件对 `/` 返回 `Cache-Control: no-cache`，对其他静态路径返回 `max-age=604800`；SPA fallback 的 `index.html` 也会返回 `no-cache`。ESA/CDN 配置应尊重这个设计，避免把 HTML 或 API 响应缓存住。

## 3. DNS 规划

先配置源站域名：

```text
1tok-origin.xhh.club  A  <阿里云 ECS 公网 IPv4>
ct.xhh.club           A  <阿里云 ECS 公网 IPv4>
```

公开域名按边缘服务控制台给出的 CNAME 配置：

```text
1tok.xhh.club      CNAME  <阿里云 ESA 分配的 CNAME>
cheaptoken.io      CNAME  <Cloudflare 分配或代理的 CNAME/记录>
www.cheaptoken.io  CNAME  <Cloudflare 分配或代理的 CNAME/记录>
```

不要把公开域名直接 A 到 ECS。这样用户永远访问边缘网络，源站只承担回源。

`ct.xhh.club` 是预发布测试域，可以先 A 到 ECS 直连源站，并在 Nginx 加 `X-Robots-Tag: noindex, nofollow`，避免被搜索引擎收录。等 `cheaptoken.io` Cloudflare 规则跑稳后，再把正式流量切过去。

## 4. 初始化 Ubuntu Server

首次登录服务器时，如果你拿到的是 `root` 用户，先创建一个带 sudo 权限的普通用户 `ubuntu`，后续部署都用这个用户执行：

```bash
adduser ubuntu
usermod -aG sudo ubuntu

# 如果 root 用户已经配置了 SSH key，把登录 key 复制给 ubuntu 用户。
mkdir -p /home/ubuntu/.ssh
if [ -f /root/.ssh/authorized_keys ]; then
  cp /root/.ssh/authorized_keys /home/ubuntu/.ssh/authorized_keys
fi
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh
if [ -f /home/ubuntu/.ssh/authorized_keys ]; then
  chmod 600 /home/ubuntu/.ssh/authorized_keys
fi

su - ubuntu
```

以下命令假设你已经切换到有 sudo 权限的 `ubuntu` 用户。

```bash
sudo apt update
sudo apt install -y ca-certificates curl gnupg git ufw nginx certbot python3-certbot-nginx

# 移除 Ubuntu 源里可能冲突的旧 Docker 包；没装过时会提示无匹配，通常可以忽略。
sudo apt remove -y docker.io docker-compose docker-compose-v2 docker-doc podman-docker containerd runc || true

# 安装 Docker CE apt 源。中国境内建议使用阿里云镜像源，避免 download.docker.com 连接失败。
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources > /dev/null <<EOF
Types: deb
URIs: https://mirrors.aliyun.com/docker-ce/linux/ubuntu
Suites: $(. /etc/os-release && echo "${UBUNTU_CODENAME:-$VERSION_CODENAME}")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker nginx
sudo usermod -aG docker ubuntu

# 配置 Docker Hub 镜像加速器。本文默认使用 DaoCloud 镜像站。
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io"
  ]
}
EOF

sudo systemctl daemon-reload
sudo systemctl restart docker

# 当前 SSH 会话可能还没刷新 docker 组权限，先用 sudo 验证 Docker 能拉镜像。
sudo docker run --rm hello-world
docker compose version
```

之后退出 SSH，再重新登录 `ubuntu` 用户，让 docker 组权限正式生效。重登后执行 `groups` 应该能看到 `docker`，后续就可以不加 `sudo` 使用 Docker。

如果 `docker run --rm hello-world` 停在 `Unable to find image 'hello-world:latest' locally`，通常不是 Docker 没装好，而是 Docker Hub 镜像拉取被卡住。先确认 `/etc/docker/daemon.json` 里已经配置了 DaoCloud 镜像站，再重启 Docker 后重试：

```bash
sudo systemctl restart docker
docker info | sed -n '/Registry Mirrors/,+5p'
docker run --rm hello-world
```

如果这里不是超时，而是对某个镜像返回 `403 Forbidden`，通常也不是 `docker login` 能解决的问题，而是当前镜像站对该镜像代理失败或临时拒绝。此时优先换一个可用镜像站；如果多个镜像站都不稳定，再回到 ACR 同步镜像方案。

如果阿里云 Docker CE 镜像源也临时不可用，可以先用 Ubuntu 系统源兜底。系统源版本通常旧一些，但对本项目的 Compose 部署够用：

```bash
sudo rm -f /etc/apt/sources.list.d/docker.sources /etc/apt/keyrings/docker.asc
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
docker --version
docker compose version
```

开启基础防火墙：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Docker 发布端口会操作 iptables。本文的 Compose 只绑定 `127.0.0.1:3000`，公网无法直接访问应用端口；PostgreSQL 和 Redis 不发布端口。

## 5. 准备项目目录与密钥

数据盘挂载到 `/data` 后，项目放在 `/data/project/1tok`。运行期数据统一放到仓库内的 `runtime/` 目录，避免和源码、Git 跟踪文件混在一起；PostgreSQL 和 Redis 也使用绑定挂载放在这里，不使用 Docker named volume，确保数据真正落在 `/data` 数据盘。

```bash
sudo mkdir -p /data/project
sudo chown -R "$USER:$USER" /data/project

cd /data/project
git clone https://cnb.cool/gzqichang/1tok 1tok
cd /data/project/1tok

mkdir -p runtime/{app-data,logs,backups,postgres,redis}
printf '\n.env\ndocker-compose.prod.yml\nruntime/\nbackup.sh\n' >> .git/info/exclude

umask 077
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 24)
REDIS_PASSWORD=$(openssl rand -hex 24)
SESSION_SECRET=$(openssl rand -hex 32)
CRYPTO_SECRET=$(openssl rand -hex 32)
ORIGIN_SECRET=$(openssl rand -hex 32)
ARGUS_DJANGO_SECRET_KEY=$(openssl rand -hex 48)

# 应用镜像来自当前 CNB 仓库的 Docker 制品库，由 .cnb.yml 自动构建并推送 latest。
NEW_API_IMAGE=docker.cnb.cool/gzqichang/1tok:latest
POSTGRES_IMAGE=postgres:15
REDIS_IMAGE=redis:7

# Argus / CheapToken
ARGUS_DATABASE_URL=postgresql://newapi:${POSTGRES_PASSWORD}@postgres:5432/argus
ARGUS_REDIS_URL=redis://:${REDIS_PASSWORD}@redis:6379/2
ARGUS_CACHE_KEY_PREFIX=argus
ARGUS_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
ARGUS_EMAIL_HOST=
ARGUS_EMAIL_PORT=587
ARGUS_EMAIL_USE_TLS=1
ARGUS_EMAIL_HOST_USER=
ARGUS_EMAIL_HOST_PASSWORD=
ARGUS_EMAIL_FROM="CheapToken <noreply@cheaptoken.io>"
ARGUS_EPAY_ENABLED=0
ARGUS_EPAY_URL=
ARGUS_EPAY_PID=
ARGUS_EPAY_KEY=
ARGUS_EPAY_NOTIFY_URL=https://ct.xhh.club/pricing/epay/notify/
ARGUS_EPAY_RETURN_URL=https://ct.xhh.club/pricing/epay/return/
EOF

cat .env
```

把输出保存到你的密码管理器。`SESSION_SECRET`、`CRYPTO_SECRET` 和 `ARGUS_DJANGO_SECRET_KEY` 后续不要随意更换，否则会影响登录会话、加密数据读取和 Argus Cookie 签名。

`NEW_API_IMAGE` 不使用原项目的 Docker Hub 镜像空间，因为你没有那个镜像仓库的写入权限。当前项目代码托管在 CNB，最省事的做法是使用 CNB 自带 Docker 制品库：每次 push 到 `1tok-main` 后，由 CNB 云原生构建把当前仓库打成 `docker.cnb.cool/gzqichang/1tok:latest`，服务器更新时只需要拉取这个 latest。

如果代码仓库或 Docker 制品是私有的，服务器第一次拉取前需要登录 CNB Docker 制品库。到 CNB「个人设置」>「访问令牌」创建一个访问令牌，授权范围选择制品库 `registry-package` 读权限，使用范围指定当前仓库。然后在服务器执行：

```bash
docker login docker.cnb.cool -u cnb -p '<CNB_ACCESS_TOKEN>'
docker pull docker.cnb.cool/gzqichang/1tok:latest
```

如果仓库和制品公开，匿名拉取也可以，但生产环境更建议使用私有制品 + 服务器只读 token。

PostgreSQL 和 Redis 仍来自 Docker Hub 官方镜像。如果后续 `docker compose pull postgres redis` 报 `registry-1.docker.io` 超时，说明 Docker Hub 访问仍不稳定。此时可以继续依赖 `/etc/docker/daemon.json` 里的 Docker Hub 镜像加速器，或只把数据库与 Redis 镜像同步到阿里云 ACR/其他镜像仓库。例如：

```dotenv
POSTGRES_IMAGE=registry.cn-hangzhou.aliyuncs.com/<你的命名空间>/postgres:15
REDIS_IMAGE=registry.cn-hangzhou.aliyuncs.com/<你的命名空间>/redis:7
```

这里的 ACR 镜像可以通过阿里云 ACR 的镜像同步能力，或在一台能访问 Docker Hub 的机器上 `pull/tag/push` 得到。应用镜像不需要再放到 ACR，优先使用 CNB Docker 制品库即可。

如果你暂时不想创建任何额外镜像仓库，就先只保留 CNB 应用镜像，并让 PostgreSQL/Redis 继续通过 Docker Hub 镜像加速器拉取：

```dotenv
NEW_API_IMAGE=docker.cnb.cool/gzqichang/1tok:latest
POSTGRES_IMAGE=postgres:15
REDIS_IMAGE=redis:7
```

这种方式不需要 ACR 命名空间，但要求 `/etc/docker/daemon.json` 里的 `registry-mirrors` 已经配置成可用的 Docker Hub 镜像加速器地址。本文默认使用 DaoCloud：

```json
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io"
  ]
}
```

### 5.1 配置 CNB 自动构建应用镜像

在本地仓库根目录新增 `.cnb.yml` 并提交到 `1tok-main`。这个流水线会在每次 push 后构建当前代码，并把镜像推送到当前仓库的 CNB Docker 制品库，同时覆盖 `latest` 标签：

```yaml
"1tok-main":
  push:
    - name: build-and-push-docker-image
      services:
        - docker
      stages:
        - name: docker build
          script: |
            docker build \
              -t ${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}:${CNB_COMMIT_SHORT} \
              -t ${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}:latest \
              .

        - name: push commit tag
          script: docker push ${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}:${CNB_COMMIT_SHORT}

        - name: push latest
          script: docker push ${CNB_DOCKER_REGISTRY}/${CNB_REPO_SLUG_LOWERCASE}:latest
```

CNB 流水线里内置了临时访问令牌和 Docker 制品库地址，可信的 push 事件默认具备 `registry-package:rw` 权限，因此推送到当前仓库的 Docker 制品库不需要额外配置 Docker 用户名和密码。

首次部署前，先在 CNB 页面确认最近一次 `1tok-main` 流水线已经成功，且「制品」里能看到 `docker.cnb.cool/gzqichang/1tok:latest`。服务器上的 `docker compose pull` 才会拉到你自己的 1tok 镜像，而不是原项目镜像。

## 6. 写入生产 Docker Compose 文件

仓库自带 `docker-compose.yml` 可作为参考，不建议在服务器上直接覆盖它。这里单独写 `docker-compose.prod.yml`，后续更新源码时更清爽。

```bash
cd /data/project/1tok

cat > docker-compose.prod.yml <<'EOF'
services:
  new-api:
    image: ${NEW_API_IMAGE}
    container_name: new-api
    restart: unless-stopped
    command: --log-dir /app/logs
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - ./runtime/app-data:/data
      - ./runtime/logs:/app/logs
    environment:
      SQL_DSN: postgresql://newapi:${POSTGRES_PASSWORD}@postgres:5432/newapi
      REDIS_CONN_STRING: redis://:${REDIS_PASSWORD}@redis:6379
      SESSION_SECRET: ${SESSION_SECRET}
      CRYPTO_SECRET: ${CRYPTO_SECRET}
      TZ: Asia/Shanghai
      ERROR_LOG_ENABLED: "true"
      BATCH_UPDATE_ENABLED: "true"
      NODE_NAME: 1tok-aliyun-ecs-1
      STREAMING_TIMEOUT: "300"
      STREAM_SCANNER_MAX_BUFFER_MB: "128"
      MAX_REQUEST_BODY_MB: "128"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O - http://localhost:3000/api/status | grep -o '\"success\":\\s*true' || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - 1tok

  argus:
    build:
      context: .
      dockerfile: argus/Dockerfile
    image: cheaptoken-argus:local
    container_name: argus
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    environment:
      DJANGO_DEBUG: "0"
      DJANGO_SECRET_KEY: ${ARGUS_DJANGO_SECRET_KEY}
      ARGUS_ALLOWED_HOSTS: ct.xhh.club,cheaptoken.io,www.cheaptoken.io
      ARGUS_CSRF_TRUSTED_ORIGINS: https://ct.xhh.club,https://cheaptoken.io,https://www.cheaptoken.io
      ARGUS_SECURE_SSL_REDIRECT: "1"
      ARGUS_SESSION_COOKIE_SECURE: "1"
      ARGUS_CSRF_COOKIE_SECURE: "1"
      ARGUS_SECURE_HSTS_SECONDS: "31536000"
      ARGUS_DATABASE_URL: ${ARGUS_DATABASE_URL}
      ARGUS_DB_SCHEMA: ""
      ARGUS_REDIS_URL: ${ARGUS_REDIS_URL}
      ARGUS_CACHE_KEY_PREFIX: ${ARGUS_CACHE_KEY_PREFIX}
      ARGUS_EMAIL_BACKEND: ${ARGUS_EMAIL_BACKEND}
      ARGUS_EMAIL_HOST: ${ARGUS_EMAIL_HOST}
      ARGUS_EMAIL_PORT: ${ARGUS_EMAIL_PORT}
      ARGUS_EMAIL_USE_TLS: ${ARGUS_EMAIL_USE_TLS}
      ARGUS_EMAIL_HOST_USER: ${ARGUS_EMAIL_HOST_USER}
      ARGUS_EMAIL_HOST_PASSWORD: ${ARGUS_EMAIL_HOST_PASSWORD}
      ARGUS_EMAIL_FROM: ${ARGUS_EMAIL_FROM}
      ARGUS_EPAY_ENABLED: ${ARGUS_EPAY_ENABLED}
      ARGUS_EPAY_URL: ${ARGUS_EPAY_URL}
      ARGUS_EPAY_PID: ${ARGUS_EPAY_PID}
      ARGUS_EPAY_KEY: ${ARGUS_EPAY_KEY}
      ARGUS_EPAY_NOTIFY_URL: ${ARGUS_EPAY_NOTIFY_URL}
      ARGUS_EPAY_RETURN_URL: ${ARGUS_EPAY_RETURN_URL}
      TZ: Asia/Shanghai
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request; request = urllib.request.Request('http://127.0.0.1:8000/', headers={'Host': 'ct.xhh.club', 'X-Forwarded-Proto': 'https'}); urllib.request.urlopen(request, timeout=5).read()\" || exit 1"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - 1tok

  postgres:
    image: ${POSTGRES_IMAGE}
    container_name: 1tok-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: newapi
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: newapi
      TZ: Asia/Shanghai
    volumes:
      - ./runtime/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U newapi -d newapi"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - 1tok

  redis:
    image: ${REDIS_IMAGE}
    container_name: 1tok-redis
    restart: unless-stopped
    command: /bin/sh -c 'redis-server --appendonly yes --requirepass "$$REDIS_PASSWORD"'
    environment:
      REDIS_PASSWORD: ${REDIS_PASSWORD}
      TZ: Asia/Shanghai
    volumes:
      - ./runtime/redis:/data
    healthcheck:
      test: ["CMD-SHELL", "redis-cli -a \"$${REDIS_PASSWORD}\" ping | grep PONG"]
      interval: 10s
      timeout: 5s
      retries: 5
    networks:
      - 1tok

networks:
  1tok:
    driver: bridge
EOF

docker compose -f docker-compose.prod.yml config --images
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml build argus
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
curl -i http://127.0.0.1:3000/api/status
curl -i -H 'Host: ct.xhh.club' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/
```

如果 `/api/status` 返回 JSON 且包含 `"success":true`，说明 new-api 已经起来。如果 `127.0.0.1:8000` 返回 CheapToken 首页 HTML，说明 Argus/Gunicorn 已经起来。Argus 容器启动时会自动确认 `argus` database 存在；如果当前 PostgreSQL 用户没有 `CREATEDB` 权限，需要先用管理员账号手动执行 `CREATE DATABASE argus;`。

首次部署或 Argus 代码包含迁移时执行：

```bash
docker compose -f docker-compose.prod.yml exec argus python manage.py migrate
docker compose -f docker-compose.prod.yml exec argus python manage.py check --deploy
```

需要管理后台时创建 Django 管理员：

```bash
docker compose -f docker-compose.prod.yml exec argus python manage.py createsuperuser
```

## 7. 配置源站 Nginx 与 HTTPS

如果 `1tok.xhh.club` 的 ESA 证书也准备由源站 certbot 续签，然后再同步到 ESA，那么公开域名也要写进 Nginx 的 `server_name`。这是因为 Let's Encrypt 的 HTTP-01 验证会访问公开域名的 `/.well-known/acme-challenge/*`，请求先到 ESA，再由 ESA 回源到 ECS；源站 Nginx 必须能按这个 Host 接住验证文件。`cheaptoken.io` 如果使用 Cloudflare 托管证书，也可以不把正式证书续签放在源站；但源站 Nginx 仍需有覆盖 `cheaptoken.io` 的证书供 Cloudflare HTTPS 回源校验。

先写入只用于签证书的 HTTP 配置：

```bash
sudo mkdir -p /var/www/certbot

sudo tee /etc/nginx/sites-available/1tok-origin.conf > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
  server_name 1tok-origin.xhh.club 1tok.xhh.club;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

  server {
    listen 80;
    listen [::]:80;
    server_name ct.xhh.club cheaptoken.io www.cheaptoken.io;

    location ^~ /.well-known/acme-challenge/ {
      root /var/www/certbot;
    }

    location / {
      return 301 https://$host$request_uri;
    }
  }
EOF

sudo ln -sf /etc/nginx/sites-available/1tok-origin.conf /etc/nginx/sites-enabled/1tok-origin.conf
sudo nginx -t
sudo systemctl reload nginx

sudo certbot certonly --webroot -w /var/www/certbot \
  --cert-name 1tok \
  -d 1tok-origin.xhh.club \
  -d 1tok.xhh.club

sudo certbot certonly --webroot -w /var/www/certbot \
  --cert-name cheaptoken \
  -d ct.xhh.club \
  -d cheaptoken.io \
  -d www.cheaptoken.io
```

前提是 `1tok.xhh.club` 已经接入阿里云 ESA，并且 ESA 对 `/.well-known/acme-challenge/*` 配置为不缓存、不过滤参数、直接回源；首次签发证书前，不要让 ESA 在这个路径上强制跳 HTTPS。`cheaptoken.io` 接入 Cloudflare 后，也要给 `/.well-known/acme-challenge/*` 保留直接回源或改用 DNS-01 续签。续签脚本同步证书时，证书文件路径使用：

```text
/etc/letsencrypt/live/1tok/fullchain.pem
/etc/letsencrypt/live/1tok/privkey.pem
/etc/letsencrypt/live/cheaptoken/fullchain.pem
/etc/letsencrypt/live/cheaptoken/privkey.pem
```

写入 WebSocket map 和源站密钥 map。这里的 `ORIGIN_SECRET` 来自 `/data/project/1tok/.env`，后面阿里云 ESA 回源必须携带同样的请求头。

```bash
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)

sudo sh -c "cat > /etc/nginx/conf.d/1tok-maps.conf" <<EOF
map_hash_bucket_size 128;

map \$http_upgrade \$connection_upgrade {
    default upgrade;
    '' close;
}

map \$http_x_1tok_origin_secret \$origin_secret_ok {
    default 0;
  "$ORIGIN_SECRET" 1;
}

map \$host \$argus_robots_tag {
    default "";
    ct.xhh.club "noindex, nofollow";
}
EOF
```

如果这里执行 `sudo nginx -t` 报错 `could not build map_hash, you should increase map_hash_bucket_size: 64`，说明当前 `map` 的键太长，直接把 `/etc/nginx/conf.d/1tok-maps.conf` 文件顶部加上下面这行，再重新检测即可：

```bash
sudo sed -i '1imap_hash_bucket_size 128;\n' /etc/nginx/conf.d/1tok-maps.conf
sudo nginx -t
sudo systemctl reload nginx
```

如果极少数环境里 `128` 仍然不够，再改成 `256`。

再写入完整反代配置：

```bash
sudo tee /etc/nginx/sites-available/1tok-origin.conf > /dev/null <<'EOF'
upstream 1tok_app {
    server 127.0.0.1:3000;
    keepalive 64;
}

upstream argus_app {
  server 127.0.0.1:8000;
  keepalive 32;
}

server {
    listen 80;
    listen [::]:80;
  server_name 1tok-origin.xhh.club 1tok.xhh.club;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$host$request_uri;
    }
}

  server {
    listen 80;
    listen [::]:80;
    server_name ct.xhh.club cheaptoken.io www.cheaptoken.io;

    location ^~ /.well-known/acme-challenge/ {
      root /var/www/certbot;
    }

    location / {
      return 301 https://$host$request_uri;
    }
  }

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
  server_name 1tok-origin.xhh.club 1tok.xhh.club;

    ssl_certificate /etc/letsencrypt/live/1tok/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/1tok/privkey.pem;

    access_log /var/log/nginx/1tok.access.log;
    error_log /var/log/nginx/1tok.error.log warn;

    client_max_body_size 128m;

    set $block_origin 1;
    if ($origin_secret_ok = 1) {
        set $block_origin 0;
    }
    if ($uri = /api/status) {
        set $block_origin 0;
    }
    if ($uri ~ ^/\.well-known/acme-challenge/) {
        set $block_origin 0;
    }
    if ($block_origin = 1) {
        return 403;
    }

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $host;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;

    proxy_connect_timeout 30s;
    proxy_send_timeout 600s;
    proxy_read_timeout 600s;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location ~ ^/(api|v1|v1beta|mj|suno|kling|jimeng|pg|dashboard)(/|$)|^/[^/]+/mj(/|$) {
        proxy_buffering off;
        proxy_request_buffering off;
        add_header Cache-Control "no-store, no-cache, must-revalidate, private, max-age=0" always;
        proxy_pass http://1tok_app;
    }

    location ^~ /assets/ {
        expires 7d;
        add_header Cache-Control "public, max-age=604800, immutable" always;
        proxy_pass http://1tok_app;
    }

    location ~* \.(?:ico|png|jpg|jpeg|gif|svg|webp|css|js|woff2?|ttf|map|txt)$ {
        expires 1d;
        add_header Cache-Control "public, max-age=86400" always;
        proxy_pass http://1tok_app;
    }

    location / {
        add_header Cache-Control "no-cache" always;
        proxy_pass http://1tok_app;
    }
}

  server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name ct.xhh.club cheaptoken.io www.cheaptoken.io;

    ssl_certificate /etc/letsencrypt/live/cheaptoken/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/cheaptoken/privkey.pem;

    access_log /var/log/nginx/argus.access.log;
    error_log /var/log/nginx/argus.error.log warn;

    client_max_body_size 16m;

    add_header X-Robots-Tag $argus_robots_tag always;

    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host $host;

    proxy_connect_timeout 30s;
    proxy_send_timeout 120s;
    proxy_read_timeout 120s;

    location ^~ /.well-known/acme-challenge/ {
      root /var/www/certbot;
    }

    location ^~ /static/ {
      expires 7d;
      add_header Cache-Control "public, max-age=604800, immutable" always;
      proxy_pass http://argus_app;
    }

    location ~ ^/(account|auth|watchlist|comparison|pricing|admin)(/|$) {
      add_header Cache-Control "no-store, no-cache, must-revalidate, private, max-age=0" always;
      proxy_pass http://argus_app;
    }

    location / {
      add_header Cache-Control "no-cache" always;
      proxy_pass http://argus_app;
    }
  }
EOF

sudo nginx -t
sudo systemctl reload nginx
```

验证源站：

```bash
curl -i https://1tok-origin.xhh.club/api/status

ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/assets/
```

第一条 `/api/status` 允许无密钥访问，方便健康检查。其他路径无密钥会返回 403，阿里云 ESA 回源时需要注入 `X-1tok-Origin-Secret`。

## 8. 阿里云 ESA 与 Cloudflare 配置

当前边缘层分成两套：

- `1tok.xhh.club` 已经迁到阿里云 ESA，重点是动态 API、SSE、WebSocket、长耗时图片生成请求全部绕过缓存并保持长回源超时。
- `cheaptoken.io` 和 `www.cheaptoken.io` 后续走 Cloudflare，重点是动态 HTML、登录验证码、Watchlist、支付回调不缓存，只有 `/static/*` 等静态资源缓存。
- `ct.xhh.club` 是 Argus 测试域，直连源站 Nginx，不接 Cloudflare，不收录。

同目录旧文档 [aliyun-esa-migration-plan.md](aliyun-esa-migration-plan.md) 的有效内容已经合并到本节；日常部署以本文为准。

### 8.1 1tok 阿里云 ESA 基础回源

| 项 | 值 |
| --- | --- |
| 加速域名 | `1tok.xhh.club` |
| 源站类型 | 域名源站 |
| 源站地址 | `1tok-origin.xhh.club` |
| 回源协议 | HTTPS |
| 回源端口 | 443 |
| 回源 Host | `1tok-origin.xhh.club` |
| 回源 SNI | `1tok-origin.xhh.club` |
| 回源请求头 | `X-1tok-Origin-Secret: <ORIGIN_SECRET>` |
| 查询字符串 | 保留，不做参数过滤 |
| 压缩 | 开启 gzip/br 均可 |
| HTTP/2/HTTP/3 | 用户侧可开启；回源保持 HTTPS 即可 |
| WebSocket | 必须开启，至少覆盖 `/v1/realtime` |
| 回源 HTTP 请求超时 | 600 秒，若控制台最大值不足则设最大值 |

如果 ESA 支持回源证书校验，开启并校验 `1tok-origin.xhh.club`。ESA 必须通过转换规则向所有回源请求添加：

```text
X-1tok-Origin-Secret: <ORIGIN_SECRET>
```

源站 Nginx 会拒绝缺少该 header 的普通路径请求，只放行 `/api/status` 和 `/.well-known/acme-challenge/*`。

### 8.2 1tok 阿里云 ESA 规则

规则优先级从高到低配置。实际控制台字段名可能不同，核心意图不变：动态请求绕过缓存、禁优化、长超时；静态资源才缓存。

| 优先级 | 匹配 | 策略 |
| --- | --- | --- |
| 1 | `/.well-known/acme-challenge/*` | 不缓存；直接回源；用于 certbot HTTP-01 签发和续签 |
| 2 | `/v1/images/generations*`、`/images/generations*`、`/v1/images/edits*` | 不缓存；允许 POST；禁压缩/改写/图片优化；回源超时 600 秒或最大值；WAF/Bot 观察或放行 |
| 3 | <code>^/(api&#124;v1&#124;v1beta&#124;mj&#124;suno&#124;kling&#124;jimeng&#124;pg&#124;dashboard)(/&#124;$)</code> 和 <code>^/[^/]+/mj(/&#124;$)</code> | 不缓存；保留 query/body/header；允许业务方法回源；SSE/WebSocket 长连接；回源超时 600 秒或最大值 |
| 4 | `/`、`*.html`、无扩展路径 | 不缓存或 TTL 0；每次回源校验；用于 React SPA 入口和前端路由 |
| 5 | `/assets/*` | 缓存 7 到 30 天；可开启 immutable |
| 6 | `*.ico`、`*.png`、`*.jpg`、`*.jpeg`、`*.gif`、`*.svg`、`*.webp`、`*.css`、`*.js`、`*.woff`、`*.woff2`、`*.ttf`、`*.txt` | 缓存 1 到 7 天 |
| 7 | 默认规则 | 不缓存 |

动态 API 路径必须保留这些特性：

- 保留 `Authorization`、`Content-Type`、请求 body 和 query string。
- 不忽略参数，不重写 body，不做 HTML/JS/CSS/图片优化。
- 对 `text/event-stream` 不压缩、不聚合、不缓冲。
- `/v1/realtime` 开启 WebSocket/Upgrade 透传。
- WAF、Bot、CC 防护先用观察模式，避免挑战页误伤 SDK、curl、长连接 POST。

图片生成路径要放在通用 `/v1/*` 规则之前。它不是 SSE，但属于长耗时动态 POST；如果仍出现 ESA `524`，优先检查是否命中图片专项规则、回源超时是否足够、WAF/Bot 是否接管、ESA 日志里边缘耗时和回源耗时是否卡在固定阈值。

### 8.3 Argus / CheapToken Cloudflare 基础回源

| 项 | 值 |
| --- | --- |
| 加速域名 | `cheaptoken.io`、`www.cheaptoken.io` |
| 源站类型 | 域名源站 |
| 源站地址 | `ct.xhh.club` 或单独的 CheapToken 源站域名 |
| 回源协议 | HTTPS |
| 回源端口 | 443 |
| 回源 Host | `cheaptoken.io` |
| 回源 SNI | `cheaptoken.io` |
| 查询字符串 | 保留，不做参数过滤 |
| 压缩 | 静态资源可开启 gzip/br；动态 HTML 不依赖边缘压缩，不做 HTML 改写 |
| WebSocket | 不需要，除非后续 Argus 增加实时功能 |

Argus 当前不走 `X-1tok-Origin-Secret` 源站密钥拦截，因为 `ct.xhh.club` 还承担测试域直连。正式只允许 Cloudflare 回源后，可以给 Argus 单独增加回源密钥 header，或改用 Cloudflare 回源 IP 白名单。

### 8.4 Argus / CheapToken Cloudflare 规则

| 优先级 | 匹配 | 策略 |
| --- | --- | --- |
| 1 | `/.well-known/acme-challenge/*` | 不缓存；直接回源；用于证书签发和续签 |
| 2 | <code>^/(account&#124;auth&#124;watchlist&#124;comparison&#124;pricing&#124;admin)(/&#124;$)</code> | 不缓存；允许 POST 直接回源；遵循源站 `Cache-Control` |
| 3 | `/preview-site/` | 不缓存；允许 POST 直接回源 |
| 4 | `/`、`*.html`、无扩展路径 | 不缓存或 TTL 0；每次回源校验 |
| 5 | `/static/*` | 缓存 7 到 30 天；可开启 immutable |
| 6 | `/favicon.ico`、图片、CSS、JS、字体 | 缓存 1 到 7 天 |
| 7 | 默认规则 | 不缓存 |

Cloudflare 上不要给登录、验证码、Watchlist 和支付路径配置 Cache Everything。`/pricing/epay/notify/` 必须允许 POST 回源；`/pricing/epay/return/` 也不要缓存。`ct.xhh.club` 保持 noindex 测试域，不建议接入搜索引擎或投放流量。

### 8.5 1tok ESA 验收

基础 HTTP：

```bash
curl -i https://1tok.xhh.club/api/status
curl -i https://1tok.xhh.club/api/pricing
curl -i https://1tok-origin.xhh.club/api/status
```

源站保护：

```bash
curl -i https://1tok-origin.xhh.club/
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/
```

预期是不带密钥访问普通路径返回 403，带密钥访问返回正常页面或响应。

SSE 流式验证：

```bash
python3 bin/stream_acceptance_test.py \
  --base-url https://1tok.xhh.club/v1 \
  --origin-base-url https://1tok-origin.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --origin-secret '<ORIGIN_SECRET>' \
  --model '<MODEL>' \
  --prompt both \
  --runs 1 \
  --save-dir ./tmp/stream-check
```

通过标准：`Content-Type` 包含 `text/event-stream`，首个 `data:` chunk 很快出现，后续 chunk 持续逐段输出，`1tok.xhh.club` 与 `1tok-origin.xhh.club` 的首个 data 延迟和总耗时接近，不应固定多出几十秒到上百秒。

图片生成验证：

```bash
python3 bin/gpt_image_test.py \
  --base-url https://1tok.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --quality low \
  --size 1024x1024 \
  --timeout 300 \
  --retries 0
```

如果 `1tok.xhh.club` 返回 `524`，而 `1tok-origin.xhh.club` 对同类请求成功，则优先排查 ESA 图片专项规则和回源超时，而不是先怀疑上游模型。

### 8.6 Argus / CheapToken 验收

```bash
curl -i https://ct.xhh.club/
curl -i https://ct.xhh.club/pricing/billing.html
curl -I https://ct.xhh.club/ | grep -i x-robots-tag
```

预期：页面返回 200，测试域响应包含 `X-Robots-Tag: noindex, nofollow`。

Cloudflare 接好后验证正式域名：

```bash
curl -i https://cheaptoken.io/
curl -i https://cheaptoken.io/pricing/billing.html
curl -i -X POST https://cheaptoken.io/auth/send-code/ -d 'email=test@example.com'
```

第三条只用于确认请求能回源；不要对真实邮箱反复压测。正式验收还需要走一次邮箱验证码登录、Watchlist 添加站点、首页匿名预览、套餐下单和易支付 notify/return。

## 9. 应用首次初始化

ESA 生效后，访问公开域名完成初始化。建议选择一个主域名作为 canonical，例如：

```text
https://1tok.xhh.club
```

进入后台后，建议设置：

- 系统访问地址/服务器地址：`https://1tok.xhh.club`
- 支付回调、OAuth callback、邮件重置链接都使用同一个主域名。
- 当前 beta 期间建议只保留这一个公开域名，避免切域名后再处理 CORS、回调地址和前端配置。

特别注意 Passkey/WebAuthn：凭据和域名强绑定。当前只用 `1tok.xhh.club` 反而更简单，后续如果再新增域名，需要把登录、支付、控制台统一引导回主域名，避免不同域名间的 Passkey、Cookie 和 OAuth 回调不一致。

Argus / CheapToken 先用测试域完成初始化：

```text
https://ct.xhh.club
```

上线前确认：

- 首页可打开，`X-Robots-Tag: noindex, nofollow` 只在 `ct.xhh.club` 生效。
- 首页输入站点 URL 后能生成预览页。
- SMTP 配置完成后，验证码能发送并登录。
- 登录后 Watchlist、添加站点、手动采集和比价页可用。
- 套餐页能创建订单。
- 易支付开启后，notify 和 return 使用同一套域名；测试阶段用 `ct.xhh.club`，正式切到 `cheaptoken.io`。

正式切换 `cheaptoken.io` 前，把 `.env` 中易支付回调改成正式域名：

```dotenv
ARGUS_EPAY_NOTIFY_URL=https://cheaptoken.io/pricing/epay/notify/
ARGUS_EPAY_RETURN_URL=https://cheaptoken.io/pricing/epay/return/
```

修改后重启 Argus：

```bash
docker compose -f docker-compose.prod.yml up -d argus
```

## 10. 日常更新

先确认本次代码已经 push 到 `origin/1tok-main`，并且 CNB 页面里对应流水线已经构建成功，`docker.cnb.cool/gzqichang/1tok:latest` 已经更新。然后在服务器备份数据库，再拉取 latest 镜像并重启应用：

```bash
cd /data/project/1tok

mkdir -p runtime/backups
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d newapi | gzip > "runtime/backups/newapi_$(date +%F_%H%M%S).sql.gz"
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d argus | gzip > "runtime/backups/argus_$(date +%F_%H%M%S).sql.gz"

git pull --ff-only
docker compose -f docker-compose.prod.yml pull new-api
docker compose -f docker-compose.prod.yml build argus
docker compose -f docker-compose.prod.yml up -d new-api
docker compose -f docker-compose.prod.yml up -d argus
docker compose -f docker-compose.prod.yml exec argus python manage.py migrate
docker compose -f docker-compose.prod.yml ps
docker image prune -f

curl -i http://127.0.0.1:3000/api/status
curl -i -H 'Host: ct.xhh.club' -H 'X-Forwarded-Proto: https' http://127.0.0.1:8000/
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/api/status
curl -i https://ct.xhh.club/
```

如果更新后前端显示异常，在阿里云 ESA 刷新这些路径即可：

```text
/
/index.html
/favicon.ico
/logo_1tok.jpg
/logo_xhh.png
/robots.txt
/static/
```

通常不需要刷新 `/assets/*`，因为构建产物文件名带 hash。Argus 更新静态资源后，如 Cloudflare 已接入 `cheaptoken.io`，刷新 `/static/*` 或对应变更文件即可。

## 11. 备份与恢复

手动备份：

```bash
cd /data/project/1tok
mkdir -p runtime/backups

docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d newapi | gzip > "runtime/backups/newapi_$(date +%F_%H%M%S).sql.gz"
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d argus | gzip > "runtime/backups/argus_$(date +%F_%H%M%S).sql.gz"
tar -czf "runtime/backups/1tok_files_$(date +%F_%H%M%S).tar.gz" runtime/app-data runtime/logs .env docker-compose.prod.yml
```

添加每日 03:20 自动备份：

```bash
cat > /data/project/1tok/backup.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

cd /data/project/1tok
mkdir -p runtime/backups

ts=$(date +%F_%H%M%S)
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d newapi | gzip > "runtime/backups/newapi_${ts}.sql.gz"
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d argus | gzip > "runtime/backups/argus_${ts}.sql.gz"
tar -czf "runtime/backups/1tok_files_${ts}.tar.gz" runtime/app-data runtime/logs .env docker-compose.prod.yml
find runtime/backups -type f -mtime +14 -delete
EOF

chmod +x /data/project/1tok/backup.sh
(crontab -l 2>/dev/null; echo '20 3 * * * /data/project/1tok/backup.sh >> /data/project/1tok/runtime/logs/backup.log 2>&1') | crontab -
```

恢复数据库前先停应用，避免恢复时仍有写入：

```bash
cd /data/project/1tok
docker compose -f docker-compose.prod.yml stop new-api argus
gunzip -c runtime/backups/newapi_YYYY-MM-DD_HHMMSS.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres psql -U newapi -d newapi
gunzip -c runtime/backups/argus_YYYY-MM-DD_HHMMSS.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres psql -U newapi -d argus
docker compose -f docker-compose.prod.yml start new-api argus
```

更严谨的恢复方式是新建空库后导入；上面的命令适合在同一套 Compose 环境里做应急恢复。

## 12. 常用运维命令

```bash
cd /data/project/1tok

# 查看容器状态
docker compose -f docker-compose.prod.yml ps

# 查看应用日志
docker compose -f docker-compose.prod.yml logs -f --tail=200 new-api
docker compose -f docker-compose.prod.yml logs -f --tail=200 argus

# 查看数据库和 Redis 日志
docker compose -f docker-compose.prod.yml logs -f --tail=100 postgres redis

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/1tok.access.log /var/log/nginx/1tok.error.log
sudo tail -f /var/log/nginx/argus.access.log /var/log/nginx/argus.error.log

# 重启应用容器
docker compose -f docker-compose.prod.yml restart new-api
docker compose -f docker-compose.prod.yml restart argus

# Argus 数据库迁移和验证码清理
docker compose -f docker-compose.prod.yml exec argus python manage.py migrate
docker compose -f docker-compose.prod.yml exec argus python manage.py purge_login_codes

# 重载 Nginx 配置
sudo nginx -t && sudo systemctl reload nginx

# 查看证书自动续期 timer
systemctl list-timers | grep certbot
```

## 13. 故障排查

### ESA 访问 403

优先检查阿里云 ESA 是否带了回源请求头：

```bash
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/
```

带密钥成功、不带密钥 403，说明源站保护正常；此时问题在 ESA 回源头没有配置或没有生效。

### 流式输出卡住或一次性吐出

检查 Nginx 动态路径里是否有：

```nginx
proxy_buffering off;
proxy_request_buffering off;
proxy_read_timeout 600s;
```

同时检查 ESA 对 `/v1/*`、`/v1beta/*` 是否关闭缓存、关闭内容优化并拉长回源超时。AI 聊天流式响应本质上不适合被边缘缓存或缓冲。

### WebSocket 连接失败

确认 Nginx 透传了：

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

并确认 ESA 开启 WebSocket/Upgrade 透传，重点路径是 `/v1/realtime`。

### 登录态异常

确认：

- `SESSION_SECRET` 没有变化。
- 用户始终在同一个主域名登录控制台。
- ESA 没有缓存 `/api/*`。
- 系统服务器地址设置为 canonical 主域名。

### 支付或 OAuth 回调异常

确认后台配置、支付平台、OAuth 应用里的 callback/return URL 全部使用同一个主域名。支付回调路径在 `/api/*` 下，必须不缓存、必须允许 POST 回源。

### Argus 页面 400 DisallowedHost

确认 Argus 环境变量包含当前访问域名：

```dotenv
ARGUS_ALLOWED_HOSTS=ct.xhh.club,cheaptoken.io,www.cheaptoken.io
```

同时确认 Nginx 透传原始 Host：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Host $host;
```

### Argus CSRF 验证失败

确认来源域名写入：

```dotenv
ARGUS_CSRF_TRUSTED_ORIGINS=https://ct.xhh.club,https://cheaptoken.io,https://www.cheaptoken.io
```

同时确认 Nginx 或 Cloudflare 传入的协议是 HTTPS：

```nginx
proxy_set_header X-Forwarded-Proto https;
```

### Argus HTTPS 重定向循环

Argus 生产默认启用 `ARGUS_SECURE_SSL_REDIRECT=1`。如果 Cloudflare 到源站是 HTTP，但用户侧是 HTTPS，需要让源站 Nginx 向 Django 传入用户侧真实协议。回源始终走 HTTPS 时使用：

```nginx
proxy_set_header X-Forwarded-Proto https;
```

### Argus 验证码无法发送

检查 SMTP 配置和 Argus 日志：

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200 argus
```

生产环境 SMTP 未配置时，验证码发送会失败。至少需要配置 `ARGUS_EMAIL_HOST`、`ARGUS_EMAIL_HOST_USER`、`ARGUS_EMAIL_HOST_PASSWORD` 和 `ARGUS_EMAIL_FROM`。

### Argus 易支付没有生成支付链接

必须同时满足：

```dotenv
ARGUS_EPAY_ENABLED=1
ARGUS_EPAY_URL=...
ARGUS_EPAY_PID=...
ARGUS_EPAY_KEY=...
```

测试阶段 notify/return 可以指向 `ct.xhh.club`；正式上线后改为 `cheaptoken.io`，并确认 Cloudflare 对 `/pricing/*` 不缓存、允许 POST 回源。

### Argus database 不存在

Argus entrypoint 会自动创建 `argus` database。如果当前 PostgreSQL 用户没有 `CREATEDB` 权限，手动执行：

```bash
docker compose -f docker-compose.prod.yml exec -T postgres psql -U newapi -d postgres -c 'CREATE DATABASE argus;'
docker compose -f docker-compose.prod.yml exec argus python manage.py migrate
```

## 14. 外部资料

- Docker 官方 Ubuntu 安装文档：https://docs.docker.com/engine/install/ubuntu/
- Docker Compose 插件安装文档：https://docs.docker.com/compose/install/linux/
- Nginx WebSocket 反代说明：https://nginx.org/en/docs/http/websocket.html
- Akamai Property Manager 缓存文档：https://techdocs.akamai.com/property-mgr/docs/caching
