# Argus 服务器部署指引

本文档用于把 Argus 部署到生产服务器。推荐形态是：Argus 作为独立 Docker 服务加入现有 1tok compose 栈，继续由 nginx 转发；Postgres 和 Redis 与 1tok 共用实例，但 Argus 使用独立 PostgreSQL database 和独立 Redis DB/key prefix。

## 目标架构

```text
用户 / CDN / ESA
  -> nginx
      -> new-api:3000
      -> argus:8000

argus
  -> postgres:5432, database: argus
  -> redis:6379, db: 2, key prefix: argus
```

建议先用 `ct.xhh.club` 直连源站 nginx 做测试；正式流量再从 `cheaptoken.io` 进入 CDN/ESA，然后回源到同一 nginx。

## 部署前准备

服务器上需要已有 1tok 的 compose 部署，并包含：

- `postgres` 服务
- `redis` 服务
- `new-api-network` 网络
- 可编辑的 nginx 配置
- 可执行 `docker-compose` 命令

Argus 镜像会使用 [Dockerfile](Dockerfile)，入口脚本是 [docker-entrypoint.sh](docker-entrypoint.sh)。容器启动时会先等待 Postgres 可用，并自动确认目标 database 存在；如果 `argus` database 不存在，会通过维护库自动执行：

```sql
CREATE DATABASE argus;
```

然后启动 Gunicorn：

```text
gunicorn argus_project.wsgi:application --bind 0.0.0.0:8000
```

数据库迁移不放在容器启动流程里，生产环境需要手动执行。

## 必填环境变量

至少需要在服务器 shell、`.env` 文件或部署系统里设置：

```bash
export ARGUS_DJANGO_SECRET_KEY='换成足够长的随机字符串'
export ARGUS_DATABASE_URL='postgresql://root:真实Postgres密码@postgres:5432/argus'
export ARGUS_DB_SCHEMA=''
export ARGUS_REDIS_URL='redis://:真实Redis密码@redis:6379/2'
export ARGUS_CACHE_KEY_PREFIX='argus'
```

默认会连接 PostgreSQL 的 `postgres` 维护库来创建目标 database。如果服务器禁用了 `postgres` 维护库，可以改成其它已存在的维护库：

```bash
export ARGUS_POSTGRES_MAINTENANCE_DB='template1'
```

`ARGUS_DJANGO_SECRET_KEY` 没有默认值，未设置时 `docker-compose up` 会直接失败，这是为了避免误用开发密钥上线。

## 域名和安全配置

当前 [docker-compose.yml](../docker-compose.yml) 中已为 Argus 预留：

```env
ARGUS_ALLOWED_HOSTS=ct.xhh.club,cheaptoken.io,www.cheaptoken.io
ARGUS_CSRF_TRUSTED_ORIGINS=https://ct.xhh.club,https://cheaptoken.io,https://www.cheaptoken.io
ARGUS_SECURE_SSL_REDIRECT=1
ARGUS_SESSION_COOKIE_SECURE=1
ARGUS_CSRF_COOKIE_SECURE=1
ARGUS_SECURE_HSTS_SECONDS=31536000
```

测试阶段不建议开启：

```env
ARGUS_SECURE_HSTS_INCLUDE_SUBDOMAINS=1
ARGUS_SECURE_HSTS_PRELOAD=1
```

这两个配置会影响域名下其它子域和浏览器预加载行为。等 `cheaptoken.io` 正式稳定后，再评估是否打开。

## 邮件发送配置

登录验证码依赖邮件发送。生产需要配置 SMTP：

```bash
export ARGUS_EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'
export ARGUS_EMAIL_HOST='smtp.example.com'
export ARGUS_EMAIL_PORT='587'
export ARGUS_EMAIL_USE_TLS='1'
export ARGUS_EMAIL_HOST_USER='noreply@cheaptoken.io'
export ARGUS_EMAIL_HOST_PASSWORD='SMTP密码'
export ARGUS_EMAIL_FROM='CheapToken <noreply@cheaptoken.io>'
```

如果 SMTP 未配置，生产环境发送验证码会失败；开发环境下会把验证码打印到控制台。

## 易支付配置

易支付默认关闭：

```bash
export ARGUS_EPAY_ENABLED='0'
```

商户参数确认后再打开：

```bash
export ARGUS_EPAY_ENABLED='1'
export ARGUS_EPAY_URL='https://你的易支付网关'
export ARGUS_EPAY_PID='商户ID'
export ARGUS_EPAY_KEY='商户密钥'
export ARGUS_EPAY_NOTIFY_URL='https://cheaptoken.io/pricing/epay/notify/'
export ARGUS_EPAY_RETURN_URL='https://cheaptoken.io/pricing/epay/return/'
```

测试域阶段可以把 notify/return 先指向：

```bash
export ARGUS_EPAY_NOTIFY_URL='https://ct.xhh.club/pricing/epay/notify/'
export ARGUS_EPAY_RETURN_URL='https://ct.xhh.club/pricing/epay/return/'
```

支付回调路径已经在 Django 路由中注册：

- `/pricing/epay/notify/`
- `/pricing/epay/return/`

## 构建和启动

在 1tok 项目根目录执行：

```bash
docker-compose build argus
docker-compose up -d argus
```

查看容器状态：

```bash
docker-compose ps argus
docker-compose logs -f argus
```

如果 Postgres 启动较慢，Argus entrypoint 会等待并重试约 60 秒。

## 初始化数据库

首次部署或代码包含迁移时执行：

```bash
docker-compose exec argus python manage.py migrate
```

创建管理员账号：

```bash
docker-compose exec argus python manage.py createsuperuser
```

清理 30 天前验证码记录可手动执行：

```bash
docker-compose exec argus python manage.py purge_login_codes
```

建议后续用服务器 cron 定期执行，例如每天凌晨：

```cron
10 3 * * * cd /path/to/1tok && docker-compose exec -T argus python manage.py purge_login_codes
```

## nginx 配置

`ct.xhh.club` 测试域可以直连源站：

```nginx
server {
    listen 443 ssl http2;
    server_name ct.xhh.club;

    add_header X-Robots-Tag "noindex, nofollow" always;

    location / {
        proxy_pass http://argus:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

正式域如果在 CDN/ESA 后面，nginx 仍然转发到 `argus:8000`。关键是让 Django 收到正确的 Host 和协议：

```nginx
proxy_set_header Host $host;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
```

如果 CDN/ESA 到源站使用 HTTP，但用户侧是 HTTPS，需要确认 CDN/ESA 传给源站的 `X-Forwarded-Proto` 是 `https`，否则 Django 的 HTTPS redirect 可能循环。

## CDN/ESA 缓存建议

第一版缓存策略应保守：

- `/static/`：可长缓存
- `/favicon.ico`：可长缓存
- 登录、验证码、Watchlist、支付、Admin：必须 bypass cache
- 动态 HTML：上线初期建议全部回源

测试域 `ct.xhh.club` 建议保留 `noindex`，不要被搜索引擎收录。

## 上线检查清单

部署后按顺序检查：

1. `docker-compose ps argus` 状态为 healthy 或 running。
2. `docker-compose logs argus` 中能看到 Gunicorn 正常启动。
3. `https://ct.xhh.club/` 首页可打开。
4. 首页输入一个站点 URL 后能生成预览页。
5. 邮箱验证码能发送并登录。
6. 登录后能进入 Watchlist。
7. 添加站点、手动采集、比价页都能使用。
8. 套餐页能创建订单。
9. 易支付开启后，支付跳转、notify、return 都能完成。
10. `docker-compose exec argus python manage.py check --deploy` 无错误。

`check --deploy` 可能提示 HSTS include subdomains 和 preload 未开启。测试域阶段这是预期状态。

## 常见问题

### DisallowedHost

确认域名写入：

```env
ARGUS_ALLOWED_HOSTS=ct.xhh.club,cheaptoken.io,www.cheaptoken.io
```

### CSRF verification failed

确认来源写入：

```env
ARGUS_CSRF_TRUSTED_ORIGINS=https://ct.xhh.club,https://cheaptoken.io,https://www.cheaptoken.io
```

同时确认 nginx/CDN 传递了 `Host` 和 `X-Forwarded-Proto`。

### HTTPS 重定向循环

Django 生产默认启用 `ARGUS_SECURE_SSL_REDIRECT=1`。如果 CDN 到源站是 HTTP，需要让源站 nginx 传入用户侧真实协议：

```nginx
proxy_set_header X-Forwarded-Proto https;
```

如果源站同时承接 HTTP/HTTPS，可以使用 `$scheme`，但要确认 CDN 回源协议不会误导 Django。

### 验证码无法发送

检查 SMTP 配置和日志：

```bash
docker-compose logs -f argus
```

生产环境 SMTP 未配置时，验证码发送会失败。

### 易支付没有生成支付链接

必须同时满足：

```env
ARGUS_EPAY_ENABLED=1
ARGUS_EPAY_URL=...
ARGUS_EPAY_PID=...
ARGUS_EPAY_KEY=...
```

notify/return URL 可以不填，系统会用当前请求域名自动生成；但正式生产更建议显式设置为 `https://cheaptoken.io/...`。

### argus database 创建失败

确认 `ARGUS_DATABASE_URL` 指向独立 database：

```env
ARGUS_DATABASE_URL=postgresql://root:真实Postgres密码@postgres:5432/argus
```

Argus entrypoint 会先连接维护库并创建 `argus` database。如果当前 Postgres 用户没有 `CREATEDB` 权限，请先用管理员账号执行：

```sql
CREATE DATABASE argus;
```

然后执行迁移：

```bash
docker-compose exec argus python manage.py migrate
```