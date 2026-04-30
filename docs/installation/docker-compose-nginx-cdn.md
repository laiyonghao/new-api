# Docker Compose + 宿主机 Nginx + CDN 部署指南

本文面向以下真实部署拓扑：

- 源站服务器：阿里云 ECS，Ubuntu Server；数据盘挂载到宿主机 `/data`。
- 应用部署：Docker Compose 启动 new-api、PostgreSQL、Redis。
- 反向代理：宿主机 Nginx 监听 80/443，反代到本机 `127.0.0.1:3000`。
- 源站域名：`1tok-origin.xhh.club`，解析到 ECS 公网 IP，只给 CDN 回源使用。
- 公开域名：`1tok.xhh.club`、`1tok.cn`、`1tok.ai`，全部接 CDN。
- CDN：`1tok.xhh.club` 和 `1tok.cn` 使用阿里云 CDN，`1tok.ai` 使用 Akamai/Linode CDN。

这套结构和你以前熟悉的 `uWSGI + Nginx` 很像：区别只是应用进程不再由宿主机直接启动，而是由 Docker Compose 管理。宿主机 Nginx 仍然负责 TLS、反代、WebSocket/SSE 透传、源站保护和统一日志。

## 1. 部署判断

建议使用“宿主机 Nginx + Docker Compose 应用栈”，原因如下：

- Nginx 放宿主机，证书、80/443 端口、防火墙、CDN 回源规则都更直观。
- Compose 内部只暴露 `127.0.0.1:3000`，PostgreSQL 和 Redis 不暴露公网。
- 以后从单机升级到 RDS/独立 Redis/多节点时，不需要改变用户访问入口。
- 这个项目有流式响应和 WebSocket 路由，Nginx 可以集中关闭代理缓冲并拉长超时。

数据库建议先用 Compose 内的 PostgreSQL。SQLite 只适合试用；MySQL 也支持，但这个项目需要同时兼容多数据库，PostgreSQL 在生产里更稳妥。如果后续用户量、账单流水或可靠性要求上来，再迁到阿里云 RDS PostgreSQL。

## 2. 项目路由与 CDN 缓存边界

根据当前代码路由，CDN 不能简单“全站缓存”。应该理解为“全站经过 CDN”，但只缓存静态资源。

必须回源且不缓存的路径：

| 路径 | 用途 | CDN 策略 |
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

可以缓存的路径：

| 路径 | 用途 | 建议 TTL |
| --- | --- | --- |
| `/assets/*` | Vite 构建产物，通常带 hash | 7 天到 30 天 |
| `/favicon.ico`、`/logo_1tok.jpg`、`/logo_xhh.png`、`/robots.txt` | public 静态文件 | 1 天到 7 天 |
| `/cover-4.webp`、`/ratio.png`、`/azure_model_name.png`、`/pay-*.png` | public 图片 | 1 天到 7 天 |

项目自己的 Web 缓存中间件对 `/` 返回 `Cache-Control: no-cache`，对其他静态路径返回 `max-age=604800`；SPA fallback 的 `index.html` 也会返回 `no-cache`。CDN 配置应尊重这个设计，避免把 HTML 或 API 响应缓存住。

## 3. DNS 规划

先配置源站域名：

```text
1tok-origin.xhh.club  A  <阿里云 ECS 公网 IPv4>
```

公开域名在 CDN 添加完成后，按 CDN 控制台给出的 CNAME 配置：

```text
1tok.xhh.club  CNAME  <阿里云 CDN 分配的 CNAME>
1tok.cn        CNAME  <阿里云 CDN 分配的 CNAME>
1tok.ai        CNAME  <Akamai/Linode CDN 分配的 CNAME>
```

不要把公开域名直接 A 到 ECS。这样用户永远访问 CDN，源站只承担回源。

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

# 应用镜像来自当前 CNB 仓库的 Docker 制品库，由 .cnb.yml 自动构建并推送 latest。
NEW_API_IMAGE=docker.cnb.cool/gzqichang/1tok:latest
POSTGRES_IMAGE=postgres:15
REDIS_IMAGE=redis:7
EOF

cat .env
```

把输出保存到你的密码管理器。`SESSION_SECRET` 和 `CRYPTO_SECRET` 后续不要随意更换，否则会影响登录会话和加密数据读取。

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
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
curl -i http://127.0.0.1:3000/api/status
```

如果 `/api/status` 返回 JSON 且包含 `"success":true`，说明应用栈已经起来。

## 7. 配置源站 Nginx 与 HTTPS

如果 `1tok.xhh.club`、`1tok.cn`、`1tok.ai` 的 CDN 证书也准备由源站 certbot 续签，然后再用脚本同步到阿里云 CDN 或 Akamai/Linode，那么这三个公开域名也要写进 Nginx 的 `server_name`。这是因为 Let's Encrypt 的 HTTP-01 验证会访问公开域名的 `/.well-known/acme-challenge/*`，请求先到 CDN，再由 CDN 回源到 ECS；源站 Nginx 必须能按这些 Host 接住验证文件。

先写入只用于签证书的 HTTP 配置：

```bash
sudo mkdir -p /var/www/certbot

sudo tee /etc/nginx/sites-available/1tok-origin.conf > /dev/null <<'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name 1tok-origin.xhh.club 1tok.xhh.club 1tok.cn 1tok.ai;

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
  -d 1tok.xhh.club \
  -d 1tok.cn \
  -d 1tok.ai
```

前提是三个公开域名已经接入 CDN，并且 CDN 对 `/.well-known/acme-challenge/*` 配置为不缓存、不过滤参数、直接回源；首次签发证书前，不要让 CDN 在这个路径上强制跳 HTTPS。续签脚本同步证书时，证书文件路径使用：

```text
/etc/letsencrypt/live/1tok/fullchain.pem
/etc/letsencrypt/live/1tok/privkey.pem
```

写入 WebSocket map 和源站密钥 map。这里的 `ORIGIN_SECRET` 来自 `/data/project/1tok/.env`，后面 CDN 回源必须携带同样的请求头。

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

server {
    listen 80;
    listen [::]:80;
    server_name 1tok-origin.xhh.club 1tok.xhh.club 1tok.cn 1tok.ai;

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
    server_name 1tok-origin.xhh.club 1tok.xhh.club 1tok.cn 1tok.ai;

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

第一条 `/api/status` 允许无密钥访问，方便健康检查。其他路径无密钥会返回 403，CDN 回源时需要注入 `X-1tok-Origin-Secret`。

## 8. CDN 配置

三个公开域名都按同一组原则配置。差别只是控制台名称不同。

### 8.1 基础回源

| 项 | 值 |
| --- | --- |
| 加速域名 | `1tok.xhh.club`、`1tok.cn`、`1tok.ai` |
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

如果 CDN 支持“回源证书校验”，开启并校验 `1tok-origin.xhh.club`。如果 CDN 不支持自定义回源请求头，就先不要启用 Nginx 的源站密钥拦截，或改用 CDN 回源 IP 白名单。

额外为证书续签配置一条最高优先级规则：`/.well-known/acme-challenge/*` 不缓存、不鉴权、不过滤参数，直接回源到 `1tok-origin.xhh.club`。这条规则不要添加 `X-1tok-Origin-Secret` 也可以，因为 Nginx 已对白名单路径放行；添加也不影响。首次签发证书前，建议让这个路径保留 HTTP 访问，不要被 CDN 强制 HTTPS 跳转卡住。

### 8.2 缓存规则优先级

按从高到低配置：

| 优先级 | 匹配 | 策略 |
| --- | --- | --- |
| 1 | `/.well-known/acme-challenge/*` | 不缓存；直接回源；用于 certbot HTTP-01 签发和续签 |
| 2 | <code>^/(api&#124;v1&#124;v1beta&#124;mj&#124;suno&#124;kling&#124;jimeng&#124;pg&#124;dashboard)(/&#124;$)</code> 和 <code>^/[^/]+/mj(/&#124;$)</code> | 不缓存；遵循源站 `Cache-Control`；禁用忽略参数；允许 POST/PUT/DELETE 直接回源；流式超时 300 到 600 秒 |
| 3 | `/`、`*.html`、无扩展路径 | 不缓存或 TTL 0；每次回源校验；用于 React SPA 入口和前端路由 |
| 4 | `/assets/*` | 缓存 7 天；可开启 immutable；更新后一般不需要刷新，因为 Vite 产物文件名带 hash |
| 5 | `*.ico`、`*.png`、`*.jpg`、`*.jpeg`、`*.gif`、`*.svg`、`*.webp`、`*.css`、`*.js`、`*.woff`、`*.woff2`、`*.ttf`、`*.txt` | 缓存 1 天到 7 天；建议 1 天起步，确认稳定后再加长 |
| 6 | 默认规则 | 不缓存 |

注意：不要缓存 `/api/status`、`/api/pricing`、`/api/notice`、`/api/about` 这类看起来像公共 GET 的接口。它们背后是后台配置，缓存后会造成控制台改了但用户看不到。

### 8.3 阿里云 CDN 建议

在阿里云 CDN 控制台中：

1. 添加加速域名 `1tok.xhh.club`、`1tok.cn`。
2. 源站填写 `1tok-origin.xhh.club`，回源协议选 HTTPS。
3. 回源 Host 设置为 `1tok-origin.xhh.club`。
4. 配置 HTTPS 证书，用户侧强制 HTTPS。
5. 开启 WebSocket。
6. 在“回源 HTTP 请求头”添加 `X-1tok-Origin-Secret`。
7. 在“缓存配置/缓存过期时间”按上表添加目录、文件后缀和默认规则。
8. 在“参数过滤”中保持不过滤参数，尤其是 `/api/*`、`/v1/*`、`/v1beta/*`。

### 8.4 Akamai/Linode CDN 建议

在 Akamai Property Manager 或 Linode CDN 对应控制台中：

1. Hostname 添加 `1tok.ai`。
2. Origin hostname 设置为 `1tok-origin.xhh.club`。
3. Forward Host Header/Origin Hostname 选择 `1tok-origin.xhh.club`，并启用 SNI。
4. Origin Custom Header 添加 `X-1tok-Origin-Secret`。
5. 对 API 路径建立 bypass cache 行为。
6. 对 `/assets/*` 和静态后缀建立 cache 行为。
7. 对 WebSocket/Upgrade 开启透传，至少覆盖 `/v1/realtime`。

## 9. 应用首次初始化

CDN 生效后，访问公开域名完成初始化。建议选择一个主域名作为 canonical，例如：

```text
https://1tok.cn
```

进入后台后，建议设置：

- 系统访问地址/服务器地址：`https://1tok.cn`
- 支付回调、OAuth callback、邮件重置链接都使用同一个主域名。
- 另外两个域名可以作为访问入口，但涉及 OAuth、支付、Passkey/WebAuthn 时，尽量统一引导到主域名。

特别注意 Passkey/WebAuthn：凭据和域名强绑定。用户在 `1tok.cn` 注册的 Passkey，不能天然在 `1tok.ai` 复用。若你计划公开三个域名，最好在 CDN 或前端入口层把登录、支付、控制台统一到主域名，其他域名更多作为访问和 API 入口。

## 10. 日常更新

先确认本次代码已经 push 到 `origin/1tok-main`，并且 CNB 页面里对应流水线已经构建成功，`docker.cnb.cool/gzqichang/1tok:latest` 已经更新。然后在服务器备份数据库，再拉取 latest 镜像并重启应用：

```bash
cd /data/project/1tok

mkdir -p runtime/backups
docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d newapi | gzip > "runtime/backups/newapi_$(date +%F_%H%M%S).sql.gz"

git pull --ff-only
docker compose -f docker-compose.prod.yml pull new-api
docker compose -f docker-compose.prod.yml up -d new-api
docker compose -f docker-compose.prod.yml ps
docker image prune -f

curl -i http://127.0.0.1:3000/api/status
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/api/status
```

如果更新后前端显示异常，CDN 刷新这些路径即可：

```text
/
/index.html
/favicon.ico
/logo_1tok.jpg
/logo_xhh.png
/robots.txt
```

通常不需要刷新 `/assets/*`，因为构建产物文件名带 hash。

## 11. 备份与恢复

手动备份：

```bash
cd /data/project/1tok
mkdir -p runtime/backups

docker compose -f docker-compose.prod.yml exec -T postgres pg_dump -U newapi -d newapi | gzip > "runtime/backups/newapi_$(date +%F_%H%M%S).sql.gz"
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
tar -czf "runtime/backups/1tok_files_${ts}.tar.gz" runtime/app-data runtime/logs .env docker-compose.prod.yml
find runtime/backups -type f -mtime +14 -delete
EOF

chmod +x /data/project/1tok/backup.sh
(crontab -l 2>/dev/null; echo '20 3 * * * /data/project/1tok/backup.sh >> /data/project/1tok/runtime/logs/backup.log 2>&1') | crontab -
```

恢复数据库前先停应用，避免恢复时仍有写入：

```bash
cd /data/project/1tok
docker compose -f docker-compose.prod.yml stop new-api
gunzip -c runtime/backups/newapi_YYYY-MM-DD_HHMMSS.sql.gz | docker compose -f docker-compose.prod.yml exec -T postgres psql -U newapi -d newapi
docker compose -f docker-compose.prod.yml start new-api
```

更严谨的恢复方式是新建空库后导入；上面的命令适合在同一套 Compose 环境里做应急恢复。

## 12. 常用运维命令

```bash
cd /data/project/1tok

# 查看容器状态
docker compose -f docker-compose.prod.yml ps

# 查看应用日志
docker compose -f docker-compose.prod.yml logs -f --tail=200 new-api

# 查看数据库和 Redis 日志
docker compose -f docker-compose.prod.yml logs -f --tail=100 postgres redis

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/1tok.access.log /var/log/nginx/1tok.error.log

# 重启应用容器
docker compose -f docker-compose.prod.yml restart new-api

# 重载 Nginx 配置
sudo nginx -t && sudo systemctl reload nginx

# 查看证书自动续期 timer
systemctl list-timers | grep certbot
```

## 13. 故障排查

### CDN 访问 403

优先检查 CDN 是否带了回源请求头：

```bash
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/
```

带密钥成功、不带密钥 403，说明源站保护正常；此时问题在 CDN 回源头没有配置或没有生效。

### 流式输出卡住或一次性吐出

检查 Nginx 动态路径里是否有：

```nginx
proxy_buffering off;
proxy_request_buffering off;
proxy_read_timeout 600s;
```

同时检查 CDN 对 `/v1/*`、`/v1beta/*` 是否关闭缓存和响应缓冲。AI 聊天流式响应本质上不适合被 CDN 缓存。

### WebSocket 连接失败

确认 Nginx 透传了：

```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

并确认 CDN 开启 WebSocket/Upgrade 透传，重点路径是 `/v1/realtime`。

### 登录态异常

确认：

- `SESSION_SECRET` 没有变化。
- 用户始终在同一个主域名登录控制台。
- CDN 没有缓存 `/api/*`。
- 系统服务器地址设置为 canonical 主域名。

### 支付或 OAuth 回调异常

确认后台配置、支付平台、OAuth 应用里的 callback/return URL 全部使用同一个主域名。支付回调路径在 `/api/*` 下，必须不缓存、必须允许 POST 回源。

## 14. 外部资料

- Docker 官方 Ubuntu 安装文档：https://docs.docker.com/engine/install/ubuntu/
- Docker Compose 插件安装文档：https://docs.docker.com/compose/install/linux/
- Nginx WebSocket 反代说明：https://nginx.org/en/docs/http/websocket.html
- Akamai Property Manager 缓存文档：https://techdocs.akamai.com/property-mgr/docs/caching
