# 阿里云 ESA 替代普通 CDN 迁移方案

本文用于把当前“宿主机 Nginx + Docker Compose + 普通 CDN”的部署，迁移到阿里云 ESA（Edge Security Acceleration，边缘安全加速）。目标是解决 AI API 流式响应经过普通 CDN 后出现的延迟放大、响应被缓冲、`client_gone` / `context canceled` 等问题，同时保留静态资源加速、源站保护、HTTPS、WebSocket 与后续安全防护能力。

当前基础部署请先阅读 [Docker Compose + 宿主机 Nginx + CDN 部署指南](docker-compose-nginx-cdn.md)。本文只讨论从普通 CDN 切到 ESA 的差异、变更步骤和验证方法。

## 1. 结论

结合当前现状，更建议直接迁移当前对外域名 `1tok.xhh.club`：

1. 保持源站域名仍为 `1tok-origin.xhh.club`，只给 ESA 回源使用。
2. 将当前对外域名 `1tok.xhh.club` 从普通 CDN 切到 ESA。
3. 用本文附带的流式验收脚本对 `1tok.xhh.club` 和 `1tok-origin.xhh.club` 做对比验收。

不建议继续用普通 CDN 承载流式 API。普通 CDN 的“缓存过期时间 0 秒”只能表示不长期复用缓存，不等于响应 chunk 会实时透传。ESA 的优势在于它是全站动态加速和边缘安全平台，有规则引擎、回源规则、网络优化、日志分析和版本管理，更适合承载动态 API、WebSocket、gRPC 和 AI 场景。

仍需注意：截至本文调研，ESA 文档明确提供动态加速、网络优化、WebSocket、gRPC、回源超时、回源 Host/SNI、转换规则和缓存规则等能力，但没有看到一个直接命名为“SSE 流式透传”的单独开关。因此迁移后必须用 `curl -N`、应用日志、Nginx 日志、ESA 日志三方验证首包时间、chunk 到达节奏和结束状态。

在你当前的 beta 阶段，只有一两个客户，而且只有 `1tok.xhh.club` 在实际使用，直接切换这个域名通常更简单。原因是：

- 不需要新增临时 Base URL，也不用通知客户改地址后再改回来。
- 不会引入新的 CORS、OAuth callback、Cookie 域、Passkey/WebAuthn 域绑定问题。
- 回滚时只需要把 `1tok.xhh.club` 的 CNAME 改回当前普通 CDN，或临时切回源站。

`1tok-temp.xhh.club` 只在一种情况下更有价值：你希望先对 ESA 做一轮完全不影响线上客户的预演，再在确认稳定后切正式域名。它能降低“第一次接 ESA 就打到生产域名”的心理压力，但最终你仍然要对 `1tok.xhh.club` 做一次正式切换，所以总变更次数其实更多。

## 2. 可行性论证

### 2.1 当前问题复盘

当前链路：

```text
客户端 -> 普通 CDN -> 源站 Nginx -> new-api -> 上游模型服务
```

已观察到：

- 上游已经完成响应，但源站服务约 100 到 120 秒后才记录接收完成。
- 成功请求和失败请求都有类似的大延迟。
- 失败时后端记录为 `client_gone` / `context canceled`。

这个现象更像是下游链路（客户端、CDN、CDN 回源连接）没有实时消费 SSE chunk，导致源站 Go 服务写下游变慢，进而反压上游读取。普通 CDN 如果没有关闭响应缓冲、流式透传或长连接动态请求能力，就很容易出现这种行为。

### 2.2 ESA 相比普通 CDN 的相关能力

阿里云 ESA 官方文档中与本项目相关的能力包括：

- “什么是 ESA”：ESA 面向网站、应用、AI 等场景提供网络层和应用层性能优化与保护，支持静态和动态资源缓存加速，使用 Anycast 和智能路由降低端到端延迟。
- “规则”：ESA 规则配置由“规则表达式 + 规则执行动作”组成，规则优先级高于全局配置，规则列表中顺序越靠前优先级越高。
- “缓存规则”：可按规则控制哪些请求缓存、哪些请求绕过缓存、边缘缓存时间、浏览器缓存时间和自定义 Cache Key。
- “转换规则”：可修改回源 HTTP 请求头、出站响应头等，适合向源站注入 `X-1tok-Origin-Secret`。
- “回源规则”：支持自定义回源 Host、回源协议和端口、回源 SNI、DNS 记录、Range 分片和回源 HTTP 请求超时时间。
- “网络优化”：支持 WebSocket、gRPC、IPv6、最大上传大小和网络优化规则；WebSocket 文档特别提示长连接场景需要回源超时与回源规则一致，并在客户端与源站之间实现心跳保活。
- “日志与数据分析”：提供实时流量数据和日志记录，用于定位服务异常和网络质量问题。
- “版本管理”：支持配置变更测试、部署和回滚。

这些能力正好对应 1tok 的核心诉求：动态 API 不缓存、流式接口减少缓冲、回源长超时、WebSocket 透传、源站保护和可观测性。

### 2.3 可行性判断

迁移到 ESA 是可行的，原因：

- 项目已经按路径区分了动态 API 和静态资源；ESA 规则引擎可以按 URI path 精确配置。
- 源站 Nginx 已经具备 SSE 友好的配置：`proxy_buffering off`、`proxy_request_buffering off`、`proxy_read_timeout 600s`。
- 源站保护目前依赖 `X-1tok-Origin-Secret`；ESA 转换规则可以给回源请求添加该 header。
- ESA 回源规则支持回源 Host、SNI 和回源 HTTP 请求超时，可匹配当前 `1tok-origin.xhh.club` 的源站证书与 Nginx server block。
- ESA 支持 WebSocket，能覆盖 `/v1/realtime`。

风险和不确定点：

- ESA 文档没有明确把 SSE 作为独立功能开关描述；必须实测 `text/event-stream` 是否逐 chunk 到达。
- 免费版/基础版/标准版/高级版的规则条数和功能不同；如果规则较多，至少建议标准版起步。
- WAF、Bot、CC 防护如果默认策略过严，可能误伤长连接 POST 请求，需要为 API stream 加白或降低动作强度。
- 若采用 NS 接入，需要迁移整个托管域的 DNS；切换面更大。对你现在的场景，更稳妥的是只让 `1tok.xhh.club` 走 CNAME 接入 ESA。

## 3. 项目实际需求

### 3.1 必须动态回源且不缓存的路径

这些路径必须绕过缓存，并保持请求方法、请求体、查询参数和鉴权头完整透传：

| 路径 | 用途 | ESA 策略 |
| --- | --- | --- |
| `/api/*` | 登录、控制台、计费、支付回调、状态、配置读取 | 绕过缓存，保留参数，允许所有业务方法回源 |
| `/v1/*` | OpenAI 兼容 API、Responses、Realtime 等 | 绕过缓存，保留参数，支持 SSE/WebSocket，长回源超时 |
| `/v1beta/*` | Gemini 兼容 API | 绕过缓存，保留参数，支持 SSE，长回源超时 |
| `/mj/*`、`/:mode/mj/*` | Midjourney API 与图片代理 | 绕过缓存，保留参数 |
| `/suno/*` | Suno 任务 API | 绕过缓存，保留参数 |
| `/kling/*` | Kling 视频 API | 绕过缓存，保留参数 |
| `/jimeng/*` | 即梦视频 API | 绕过缓存，保留参数 |
| `/pg/*` | Playground API | 绕过缓存，保留参数 |
| `/dashboard/*`、`/v1/dashboard/*` | Dashboard/Billing 兼容接口 | 绕过缓存，保留参数 |

其中最重要的是 `/v1/*` 和 `/v1beta/*`，因为它们直接承载 AI stream。

### 3.2 可以缓存的路径

| 路径 | 建议策略 |
| --- | --- |
| `/assets/*` | 边缘缓存 7 到 30 天，浏览器缓存 7 到 30 天 |
| `*.js`、`*.css`、`*.woff2`、`*.png`、`*.jpg`、`*.webp`、`*.svg` | 边缘缓存 1 到 7 天，确认稳定后可延长 |
| `/`、`*.html`、无扩展 SPA 路径 | 不缓存或遵循源站 `Cache-Control: no-cache` |

### 3.3 必须保留的请求和响应特性

动态 API 路径必须满足：

- 保留 `Authorization`。
- 保留 `Content-Type`。
- 保留请求 body，不做请求体改写。
- 保留 query string，不做参数过滤。
- 回源请求带 `X-1tok-Origin-Secret`。
- SSE 响应保留 `Content-Type: text/event-stream`。
- SSE 响应不要被压缩、聚合、HTML 优化、JS/CSS 优化或内容改写。
- 回源读取/请求超时至少 300 秒，建议 600 秒。

### 3.4 当前 ESA 图片生成问题的判断

基于当前实测，可以先把问题拆成两段：

- `https://1tok.xhh.club` 调用图片生成持续返回 `524`。
- `https://1tok-origin.xhh.club` 调用同一请求可以成功返回图片 URL。

这说明“上游生图失败”并不是当前主因。更像是 ESA 对这类长耗时、非流式、POST 动态请求的回源等待策略还没有配对。

这里要特别注意：`/v1/images/generations` 虽然不属于 SSE，但它仍然是长耗时动态 API。不能因为它最终返回的是 `application/json`，就把它和普通短平快 JSON 接口放在同一套默认 ESA 规则里。对 ESA 来说，它和 stream 一样，都需要：

- 不缓存。
- 不压缩、不改写、不做内容优化。
- 足够大的回源等待时间。
- 不被 WAF/Bot/挑战页打断。
- 高于通用 `/v1/*` 规则的单独优先级。

## 4. 推荐目标架构

### 4.1 直接切换当前域名

```text
用户浏览器/SDK
  |-- https://1tok.xhh.club      -> ESA        -> 源站 Nginx -> new-api
  |-- https://1tok-origin.xhh.club -> 源站直连 -> 源站 Nginx -> new-api
```

这是当前最简单的迁移方式。因为 `1tok.xhh.club` 已经是客户实际在用的域名，切 ESA 后前端静态资源和 API 仍然同域，不需要额外处理跨域或改 Base URL。

### 4.2 可选的临时域名预演

如果你坚持要在正式切换前先做一轮独立预演，可以额外创建：

```text
1tok-temp.xhh.club -> ESA -> 源站 Nginx -> new-api
```

这个方案的优点是可以在正式域名切换前完成控制台配置、规则验证和源站 header 验证；缺点是你最终仍然要再切一次 `1tok.xhh.club`。因此本文后续步骤都以“直接切当前域名”为主，只在必要时提及 `1tok-temp.xhh.club` 作为备选。

### 4.3 稳定后的架构

```text
用户浏览器/SDK
  -> ESA
     |-- /assets/* 静态缓存
     |-- /api/* /v1/* /v1beta/* 动态回源
     |-- WAF/Bot/日志/规则/版本管理
  -> 源站 Nginx
  -> new-api Docker Compose 应用
```

源站域名继续使用：

```text
1tok-origin.xhh.club -> ECS 公网 IP
```

公开域名：

```text
1tok.xhh.club
```

## 5. 源站服务器变更

### 5.1 Nginx 保持 SSE 友好配置

源站 Nginx 动态路径必须保持：

```nginx
location ~ ^/(api|v1|v1beta|mj|suno|kling|jimeng|pg|dashboard)(/|$)|^/[^/]+/mj(/|$) {
    proxy_buffering off;
    proxy_request_buffering off;
    add_header Cache-Control "no-store, no-cache, must-revalidate, private, max-age=0" always;
    proxy_pass http://1tok_app;
}
```

server 级别继续保持：

```nginx
proxy_http_version 1.1;
proxy_connect_timeout 30s;
proxy_send_timeout 600s;
proxy_read_timeout 600s;
```

项目本身也会设置 SSE 响应头：

```text
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Transfer-Encoding: chunked
X-Accel-Buffering: no
```

Nginx 不要开启 gzip 代理压缩，也不要在源站层对动态 API 做响应缓冲。

### 5.2 继续使用源站密钥保护

正式接入 ESA 后，不建议长期放开源站直连。继续保留现有逻辑：

```nginx
map $http_x_1tok_origin_secret $origin_secret_ok {
    default 0;
    "<ORIGIN_SECRET>" 1;
}
```

```nginx
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
```

ESA 通过转换规则向回源请求添加：

```text
X-1tok-Origin-Secret: <ORIGIN_SECRET>
```

### 5.3 临时直连放行

如果要让开发机直接访问 `1tok-origin.xhh.club` 排查问题，可以临时对 API 路径绕过源站密钥校验：

```nginx
if ($uri ~ ^/(api|v1|v1beta)(/|$)) {
    set $block_origin 0;
}
```

验证 ESA 回源头生效后，应删除这段临时放行，恢复源站保护。

### 5.4 Nginx 验证命令

```bash
sudo nginx -t
sudo systemctl reload nginx

curl -i https://1tok-origin.xhh.club/api/status

ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/api/status
curl -i https://1tok-origin.xhh.club/
```

预期：

- `/api/status` 可无密钥返回 200。
- 带密钥访问普通路径返回 200 或前端 HTML。
- 不带密钥访问普通路径返回 403。

## 6. ESA 配置方案

### 6.1 接入方式选择

优先推荐直接接入当前正式域名：

```text
1tok.xhh.club -> ESA
```

如果你想先做无感预演，也可以先加：

```text
1tok-temp.xhh.club -> ESA
```

但在当前 beta 阶段，直接切 `1tok.xhh.club` 一般更省事。

接入方式选择建议：

| 方式 | 适用场景 | 建议 |
| --- | --- | --- |
| CNAME 接入 | 只迁移 `1tok.xhh.club`，保留现有 DNS 服务商 | 当前最推荐 |
| NS 接入 | 准备把整个根域名交给 ESA 管理 | 全站迁移后再考虑 |

### 6.2 DNS 记录规划

在 ESA 或现有 DNS 服务商中保留源站 DNS：

```text
1tok-origin.xhh.club  A  <ECS 公网 IPv4>  DNS only，不开启代理加速
```

公开域名：

```text
1tok.xhh.club  CNAME  -> ESA 分配的接入地址
```

如果使用 ESA 的 NS 接入，需在 ESA DNS 中导入现有 DNS 记录，并只对需要加速的记录打开“代理加速”。源站记录必须保持 DNS only，避免回源套娃。

### 6.3 源站配置

ESA 源站配置建议：

| 配置项 | 值 |
| --- | --- |
| 源站类型 | 域名源站 |
| 源站地址 | `1tok-origin.xhh.club` |
| 回源协议 | HTTPS |
| 回源端口 | 443 |
| 回源 Host | `1tok-origin.xhh.club` |
| 回源 SNI | `1tok-origin.xhh.club` |
| 回源证书校验 | 开启，校验 `1tok-origin.xhh.club` |
| 回源 HTTP 请求超时 | 600 秒，若控制台最大值不足则设最大值 |
| 回源 301/302 跟随 | 不建议为 API 开启，避免掩盖配置错误 |

### 6.4 转换规则：添加源站密钥请求头

创建转换规则，匹配所有需要回源到源站的公开域名，当前至少包括 `1tok.xhh.club`。

下列表达式用于表达规则意图。实际配置时优先使用 ESA 控制台的可视化条件控件；如果使用表达式编辑器，请以控制台当前提示的字段名、运算符和套餐能力为准。

规则表达式示例：

```text
(http.host eq "1tok.xhh.club")
```

执行动作：修改出站请求头或回源请求头，添加：

```text
X-1tok-Origin-Secret: <ORIGIN_SECRET>
```

如果你先用临时域名预演，表达式扩展为：

```text
(http.host in {"1tok.xhh.club" "1tok-temp.xhh.club"})
```

### 6.5 缓存规则：API 绕过缓存

创建最高优先级缓存规则，匹配动态 API：

实际配置时优先使用“路径等于”加“路径前缀/通配”组合，确保既覆盖 `/api`，也覆盖 `/api/*`。下面表达式是意图示例：

```text
(http.request.uri.path eq "/api") or
(http.request.uri.path wildcard "/api/*") or
(http.request.uri.path eq "/v1") or
(http.request.uri.path wildcard "/v1/*") or
(http.request.uri.path eq "/v1beta") or
(http.request.uri.path wildcard "/v1beta/*") or
(http.request.uri.path eq "/mj") or
(http.request.uri.path wildcard "/mj/*") or
(http.request.uri.path eq "/suno") or
(http.request.uri.path wildcard "/suno/*") or
(http.request.uri.path eq "/kling") or
(http.request.uri.path wildcard "/kling/*") or
(http.request.uri.path eq "/jimeng") or
(http.request.uri.path wildcard "/jimeng/*") or
(http.request.uri.path eq "/pg") or
(http.request.uri.path wildcard "/pg/*") or
(http.request.uri.path eq "/dashboard") or
(http.request.uri.path wildcard "/dashboard/*")
```

执行动作：

```text
缓存资格：绕过缓存 / 不缓存
边缘缓存过期时间：不缓存
浏览器缓存过期时间：不缓存或遵循源站
自定义 Cache Key：不要忽略 query string
```

如果控制台没有“绕过缓存”的字样，但有“缓存资格”，应选择“不符合缓存资格”或等价选项。不要只把过期时间设置为 0；过期时间 0 不是流式透传保证。

### 6.6 缓存规则：静态资源缓存

静态资源规则优先级应低于 API 绕过缓存规则。

匹配：

```text
(http.request.uri.path wildcard "/assets/*")
```

执行动作：

```text
边缘缓存过期时间：7 天到 30 天
浏览器缓存过期时间：7 天到 30 天
```

静态后缀规则：

```text
(http.request.uri.path matches ".*\\.(js|css|png|jpg|jpeg|webp|svg|ico|woff|woff2|ttf|map|txt)$")
```

如果套餐不支持正则表达式，就使用控制台的文件后缀条件拆成多条规则，或者先只缓存 `/assets/*`。

### 6.7 缓存规则：HTML 和 SPA 入口不缓存

匹配：

```text
(http.request.uri.path eq "/") or
(http.request.uri.path wildcard "/*.html")
```

如果控制台没有 `/*.html` 这种通配表达式，就使用文件后缀条件匹配 `html`。

执行动作：

```text
缓存资格：绕过缓存 / 不缓存
浏览器缓存过期时间：不缓存或遵循源站
```

### 6.8 内容优化规则：API 禁用压缩和改写

对动态 API 路径创建内容优化规则，匹配同 6.5。

执行动作：

```text
文件压缩：关闭
Brotli：关闭
Gzip：关闭或至少排除 text/event-stream
图像优化：关闭
视频处理：关闭
HTML/JS/CSS 优化：关闭
```

原因：SSE 的关键是小 chunk 及时到达，任何压缩、聚合、改写都可能引入缓冲。

静态资源可以单独开启压缩和优化，但不能覆盖 API 规则。

### 6.9 网络优化规则：WebSocket

ESA 文档说明 WebSocket 默认可开启，也支持通过网络优化规则限制到指定域名。

建议：

```text
WebSocket：开启
匹配域名：1tok.xhh.club
重点路径：/v1/realtime
回源 HTTP 请求超时：与回源规则一致，建议 600 秒
```

同时项目或客户端需要有心跳保活。对于 SSE，项目后端已有 ping 配置能力，但当前默认是否开启取决于后台通用设置。若仍遇到中间层空闲超时，可以考虑启用 ping，并设置 15 到 30 秒。

### 6.10 WAF / Bot / CC 防护

试点阶段建议保守启用：

```text
/v1/*、/v1beta/*：不做验证码挑战，不做人机校验，不做 JS Challenge
/api/*：登录、注册、支付等可保留基础防护，但不要误伤长连接 POST
频率限制：先观察日志，不要一开始设得太低
Bot 防护：API SDK/curl/服务器调用较多，先不要强挑战
```

建议先只打开日志/观察模式，确认 stream 稳定后再逐步收紧。

### 6.11 版本管理

如果 ESA 控制台支持环境和版本管理，建议：

1. 新建一个 `esa-api-stream-pilot` 版本。
2. 在测试环境或灰度环境发布。
3. 通过 `1tok.xhh.club` 小流量验证。
4. 成功后发布到生产。
5. 保留上一版本，方便回滚。

### 6.12 图片生成专项规则：优先级高于通用 `/v1/*`

针对当前已经确认会在 ESA 下触发 `524` 的图片生成请求，建议额外创建一条单独规则，优先级放在通用 API 规则之前。

建议至少覆盖这些路径：

```text
(http.request.uri.path eq "/v1/images/generations") or
(http.request.uri.path wildcard "/v1/images/generations/*") or
(http.request.uri.path eq "/images/generations") or
(http.request.uri.path wildcard "/images/generations/*") or
(http.request.uri.path eq "/v1/images/edits") or
(http.request.uri.path wildcard "/v1/images/edits/*")
```

如果控制台支持按 Host 限制，建议同时加上：

```text
http.host eq "1tok.xhh.club"
```

执行动作建议：

```text
缓存资格：绕过缓存 / 不缓存
边缘缓存时间：不缓存
浏览器缓存时间：不缓存
查询参数：完整保留
请求方法：允许 POST 直接回源
请求体：不改写
回源 Host：1tok-origin.xhh.club
回源 SNI：1tok-origin.xhh.club
回源 HTTP 请求超时：600 秒或控制台允许的最大值
回源 301/302 跟随：关闭
文件压缩：关闭
Brotli：关闭
Gzip：关闭
内容改写：关闭
图像优化：关闭
WAF/Bot/挑战：关闭或观察模式
```

核心判断标准不是“缓存过期时间是否为 0”，而是 ESA 是否真的把这条请求视为一条长耗时动态回源请求，并且在源站最终返回 JSON 之前不会抢先超时。

如果 ESA 控制台支持按路径单独设置回源规则，就把这条图片规则的回源超时单独拉满，不要只依赖站点级默认值。

## 7. 变更步骤

### 7.1 变更前准备

记录当前状态：

```bash
dig +short 1tok.xhh.club
curl -i https://1tok-origin.xhh.club/api/status
curl -i https://1tok.xhh.club/api/status
```

确认源站：

```bash
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/api/status
```

准备一个真实 stream 测试 token 和模型，用于后续验证。

### 7.2 接入 ESA

1. 在 ESA 添加站点或子域名。
2. 配置 `1tok.xhh.club` 代理加速。
3. 源站配置为 `1tok-origin.xhh.club:443`。
4. 配置边缘证书。
5. 配置回源 Host/SNI 为 `1tok-origin.xhh.club`。
6. 配置转换规则添加 `X-1tok-Origin-Secret`。
7. 配置 API 绕过缓存规则。
8. 配置 API 禁用内容优化规则。
9. 配置 WebSocket 开启。
10. 配置回源超时 600 秒或最大值。

### 7.3 DNS 切换

如果使用 CNAME 接入：

```text
1tok.xhh.club CNAME <ESA 分配的 CNAME>
```

如果使用 NS 接入：

- 先在 ESA 导入所有现有 DNS 记录。
- `1tok-origin.xhh.club` 保持 DNS only。
- `1tok.xhh.club` 打开代理加速。
- 确认无遗漏后再切 NS。

### 7.4 是否需要临时域名

如果你只想尽快解决 streaming 问题，直接让 `1tok.xhh.club` 切 ESA 即可，不需要再引入新的中间网址。

如果你希望在正式切换前做一轮纯验收，可以额外建立：

```text
1tok-temp.xhh.club CNAME <ESA 分配的 CNAME>
```

然后用本文后面的脚本先对 `1tok-temp.xhh.club` 做 stream 验收。确认稳定后，再把正式域名 `1tok.xhh.club` 切到 ESA。同一套 ESA 规则通常可以直接复用，因此从临时域名切到正式域名是可行的；只是总操作次数会更多。

## 8. 验证方案

### 8.1 基础 HTTP 验证

```bash
curl -i https://1tok.xhh.club/api/status
curl -i https://1tok.xhh.club/api/pricing
curl -i https://1tok.xhh.club/api/about
```

预期：

- HTTP 200。
- JSON 正常。
- 源站 Nginx access log 里能看到请求。
- 不再出现 403，说明 ESA 回源头已生效。

### 8.2 源站保护验证

```bash
curl -i https://1tok-origin.xhh.club/
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -i -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" https://1tok-origin.xhh.club/
```

预期：

- 不带密钥访问普通路径返回 403。
- 带密钥访问返回正常页面或响应。
- 说明源站仍被保护，ESA 是通过回源头访问源站。

### 8.3 SSE 流式验证

使用 `curl -N`，它会关闭 curl 自身缓冲：

```bash
curl -N --http1.1 -v https://1tok.xhh.club/v1/chat/completions \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<MODEL>",
    "stream": true,
    "messages": [
      {"role": "user", "content": "请从1数到30，每个数字单独输出。"}
    ]
  }'
```

同时对比源站直连：

```bash
ORIGIN_SECRET=$(grep '^ORIGIN_SECRET=' /data/project/1tok/.env | cut -d= -f2-)
curl -N --http1.1 -v https://1tok-origin.xhh.club/v1/chat/completions \
  -H "X-1tok-Origin-Secret: $ORIGIN_SECRET" \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "<MODEL>",
    "stream": true,
    "messages": [
      {"role": "user", "content": "请从1数到30，每个数字单独输出。"}
    ]
  }'
```

通过标准：

- 首个 `data:` chunk 很快出现。
- 后续 chunk 持续逐段输出，而不是积攒后一次性吐出。
- 源站日志中 stream end reason 为 `done` 或正常 `eof`，不应大量出现 `client_gone`。
- ESA 路径与源站直连的总耗时接近，不应固定多出 100 秒左右。

### 8.4 WebSocket 验证

如果使用 `/v1/realtime`，用支持 WebSocket 的客户端或 `wscat` 验证：

```bash
npx wscat -c "wss://1tok.xhh.club/v1/realtime?..." \
  -H "Authorization: Bearer <TOKEN>"
```

预期：

- 握手成功。
- 源站 Nginx 能看到 Upgrade 请求。
- 长连接空闲时依靠业务心跳保持。

### 8.5 日志验证

源站：

```bash
sudo tail -f /var/log/nginx/1tok.access.log /var/log/nginx/1tok.error.log
docker compose -f /data/project/1tok/docker-compose.prod.yml logs -f --tail=200 new-api
```

ESA：

- 查看即时日志或日志服务。
- 筛选 `1tok.xhh.club`。
- 关注状态码、边缘耗时、回源耗时、缓存状态、WAF/Bot 动作。

### 8.6 本机重复验收脚本

仓库里新增了一个可重复运行的脚本：

```text
bin/stream_acceptance_test.py
```

它会实际发起 `stream=true` 请求，并输出以下关键信息：

- HTTP 状态码
- `Content-Type` 是否包含 `text/event-stream`
- 首个响应头到达时间
- 首个 `data:` 事件到达时间
- SSE 事件数量、总字节数
- 相邻 `data:` 事件的平均间隔与最大间隔
- `1tok.xhh.club` 与 `1tok-origin.xhh.club` 的差值对比

推荐先在开发机运行：

```bash
python3 bin/stream_acceptance_test.py \
  --base-url https://1tok.xhh.club/v1 \
  --origin-base-url https://1tok-origin.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --origin-secret '<ORIGIN_SECRET>' \
  --model claude-opus-4-7 \
  --prompt both \
  --runs 1 \
  --save-dir ./tmp/stream-check
```

如果你更想先验收临时域名，就把 `--base-url` 改成 `https://1tok-temp.xhh.club/v1`。

脚本内置了两组更容易产出长回答的编程题：

- `python`：异步任务调度器设计与完整实现
- `cpp`：现代 C++20 事件驱动网络框架设计与完整实现

常用模式：

```bash
# 只测 Python 大回答
python3 bin/stream_acceptance_test.py \
  --base-url https://1tok.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --model claude-opus-4-7 \
  --prompt python

# 连跑 3 次，看波动
python3 bin/stream_acceptance_test.py \
  --base-url https://1tok.xhh.club/v1 \
  --origin-base-url https://1tok-origin.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --origin-secret '<ORIGIN_SECRET>' \
  --model claude-opus-4-7 \
  --prompt cpp \
  --runs 3
```

验收时重点看三件事：

- `Content-Type` 必须是 `text/event-stream`
- public 与 origin 的首个 `data:` 事件延迟不要相差太大
- public 的最大 chunk 间隔不要出现固定几十秒到上百秒的异常停顿

### 8.7 图片生成验证

仓库里也有图片生成测试脚本：

```text
bin/gpt_image_test.py
```

当前更建议把它当作 ESA 图片回源验收脚本来用，而不是只拿来验证模型能力。建议分别对公开域名和源站域名跑同一组参数：

```bash
python3 bin/gpt_image_test.py \
  --base-url https://1tok.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --quality low \
  --size 1024x1024 \
  --timeout 300 \
  --retries 0

python3 bin/gpt_image_test.py \
  --base-url https://1tok-origin.xhh.club/v1 \
  --api-key '<YOUR_KEY>' \
  --quality low \
  --size 1024x1024 \
  --timeout 300 \
  --retries 0
```

如果源站要求密钥头，直接用临时放行或改造脚本添加 `X-1tok-Origin-Secret` 后再测。

通过标准：

- `1tok-origin.xhh.club` 可以稳定成功。
- `1tok.xhh.club` 不应再出现 `524`。
- 两边都成功时，public 总耗时应接近 origin，而不应卡在 ESA 的固定超时点。
- 成功响应可能返回图片 URL，而不是 base64；这属于正常现象。

### 8.8 图片生成 524 排障顺序

如果图片生成仍然出现“源站成功、ESA 返回 524”，按下面顺序排：

1. 先确认 ESA 图片专项规则优先级高于通用 `/v1/*` 规则。
2. 确认图片路径确实命中了“不缓存、禁优化、长超时”这条规则，而不是被默认缓存规则接走。
3. 确认 ESA 的回源超时是按图片路径规则单独生效，而不是仍落到较小的全局默认值。
4. 确认图片路径没有被 WAF、Bot、人机挑战或 CC 规则接管。
5. 在 ESA 日志里同时看边缘状态码、边缘耗时、回源耗时、规则命中情况。
6. 对比源站 Nginx access log 和应用日志，确认源站是否在 524 发生时已经正常写出了 200 响应。

如果 ESA 日志显示边缘在等待源站期间超时，而源站日志确认同一请求稍后成功返回，那么问题就可以继续锁定为 ESA 回源等待策略，而不是应用生成失败。

另外，当前项目里阿里异步图片通道本身存在固定轮询等待：先等待 5 秒，再按 10 秒间隔轮询任务状态。因此“上游日志显示 39.78 秒完成，而源站客户端看到 64.55 秒才成功”并不一定是 ESA 问题，有一部分可能来自应用层轮询尾延迟。对应代码在 [relay/channel/ali/image.go](relay/channel/ali/image.go#L221) 附近。

## 9. 回滚方案

### 9.1 API 域名回滚到源站直连

如果 ESA stream 仍异常，把 `1tok.xhh.club` 切回旧 CDN 或临时改回源站：

```text
1tok.xhh.club CNAME <原普通 CDN 分配的 CNAME>
```

若需要临时直连源站验证，也可以改成：

```text
1tok.xhh.club A <ECS 公网 IPv4>
```

然后在 Nginx 临时放行 API 路径，或为 `1tok.xhh.club` 建独立 server block：

```nginx
if ($host = 1tok.xhh.club) {
    set $block_origin 0;
}
```

更推荐只放行 API 路径：

```nginx
if ($uri ~ ^/(api|v1|v1beta)(/|$)) {
    set $block_origin 0;
}
```

完成回滚后：

```bash
sudo nginx -t
sudo systemctl reload nginx

curl -i https://1tok.xhh.club/api/status
```

### 9.2 ESA 配置回滚

如果使用版本管理：

1. 回滚到上一版本。
2. 观察 `/api/status` 与 stream 测试。
3. 若仍异常，再 DNS 回滚。

### 9.3 主站不受影响

如果你采用的是“直接切正式域名”方案，那么回滚影响面和切换影响面一致，但动作也更简单，只需要把 `1tok.xhh.club` 指回旧 CDN 或源站。

## 10. 推荐实施顺序

1. 源站 Nginx 恢复/确认源站密钥保护。
2. 在开发机先用 [bin/stream_acceptance_test.py](bin/stream_acceptance_test.py) 对比 `1tok.xhh.club` 与 `1tok-origin.xhh.club` 的现状。
3. 将 `1tok.xhh.club` 接入 ESA。
4. 配置 ESA 回源 Host/SNI/请求头/超时。
5. 单独配置图片生成路径规则，确保其优先级高于通用 `/v1/*`。
6. 配置 API 绕过缓存和禁用内容优化。
7. 配置 WebSocket。
8. 用 `/api/status` 验证回源头。
9. 用 [bin/stream_acceptance_test.py](bin/stream_acceptance_test.py) 验证 `Content-Type: text/event-stream` 和 chunk 透传。
10. 用 [bin/gpt_image_test.py](bin/gpt_image_test.py) 分别验证 `1tok.xhh.club` 与 `1tok-origin.xhh.club` 的图片生成结果。
11. 用真实用户请求观察 24 到 48 小时。

## 11. 成功标准

迁移成功需要同时满足：

- `/api/status`、`/api/pricing` 等公开 API 经过 ESA 返回正常。
- `/v1/*`、`/v1beta/*` stream 的首包和逐 chunk 输出与源站直连接近。
- `/v1/images/generations` 等图片接口经过 ESA 不再返回 `524`。
- 图片生成 public 与 origin 都能成功时，总耗时差值不再异常放大。
- `client_gone` 比例显著下降，不再集中出现在 100 到 120 秒左右。
- ESA 日志中 API 请求为绕过缓存或动态回源，不命中静态缓存。
- 源站 Nginx 不再出现大量 499/504。
- WAF/Bot 没有对 API stream 产生挑战或拦截。
- 源站普通路径不带 `X-1tok-Origin-Secret` 仍返回 403。

## 12. ESA 控制台检查清单

### 基础接入

- [ ] 站点已添加。
- [ ] `1tok.xhh.club` 已开启代理加速。
- [ ] `1tok-origin.xhh.club` 未开启代理加速，只作为源站 DNS。
- [ ] 边缘证书已配置。
- [ ] 回源协议为 HTTPS。
- [ ] 回源 Host 为 `1tok-origin.xhh.club`。
- [ ] 回源 SNI 为 `1tok-origin.xhh.club`。
- [ ] 回源证书校验已开启。

### API / stream

- [ ] `/api/*` 绕过缓存。
- [ ] `/v1/*` 绕过缓存。
- [ ] `/v1beta/*` 绕过缓存。
- [ ] `/v1/images/generations`、`/v1/images/edits` 有单独高优先级规则。
- [ ] 查询参数完整保留，不忽略 query string。
- [ ] POST/PUT/PATCH/DELETE 正常回源。
- [ ] API 路径关闭 Brotli/Gzip/文件压缩或至少排除 `text/event-stream`。
- [ ] API 路径关闭 HTML/JS/CSS 优化、图像优化、内容改写。
- [ ] 回源 HTTP 请求超时为 600 秒或最大值。
- [ ] 图片生成路径的回源超时单独核对过，未落回全局默认值。
- [ ] WebSocket 已开启，覆盖 `/v1/realtime`。

### 源站保护

- [ ] 转换规则添加 `X-1tok-Origin-Secret`。
- [ ] 源站不带密钥访问普通路径返回 403。
- [ ] ESA 访问 `https://1tok.xhh.club/api/status` 返回 200。

### 安全与日志

- [ ] WAF 对 `/v1/*`、`/v1beta/*` 不做挑战。
- [ ] WAF/Bot/CC 对图片生成路径不做人机挑战或阻断。
- [ ] Bot 防护不误伤 SDK/curl。
- [ ] CC/频控阈值不会清理长连接 stream。
- [ ] 即时日志或日志服务已开启。
- [ ] 可以按 Host、路径、状态码、缓存状态、回源耗时筛选。

## 13. 官方文档入口

- ESA 产品概述：https://help.aliyun.com/document_detail/2794340.html
- 将域名快速接入 ESA：https://help.aliyun.com/document_detail/2709243.html
- 规则概述：https://help.aliyun.com/document_detail/2703168.html
- 缓存规则：https://help.aliyun.com/document_detail/2703465.html
- 转换规则：https://help.aliyun.com/document_detail/2845552.html
- 回源规则：https://help.aliyun.com/document_detail/2845546.html
- 网络优化：https://help.aliyun.com/document_detail/2844731.html
