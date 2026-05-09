#!/usr/bin/env python3

import argparse
import base64
import os
import sys
import time
from pathlib import Path

from openai import APIConnectionError, APIStatusError, APITimeoutError, InternalServerError, OpenAI


DEFAULT_PROMPT = (
    "生成一张横版技术宣传插画：深色工作台上摆放着打开的笔记本电脑，屏幕里是清晰可读的 Python "
    "和现代 C++ 代码片段，周围有终端窗口、架构草图、数据流箭头和柔和的体积光。整体风格偏写实，"
    "但保留现代产品宣传图的干净构图，细节丰富，不要出现水印、logo、错别字。"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="使用 OpenAI Python SDK 调用站点提供的 gpt-image-2 图像生成接口。"
    )
    parser.add_argument(
        "--base-url",
        default="",
        help="OpenAI 兼容 Base URL，例如 https://1tok.xhh.club/v1",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API Key；未提供时尝试读取 OPENAI_API_KEY / ONEAPI_API_KEY / API_KEY",
    )
    parser.add_argument(
        "--model",
        default="gpt-image-2",
        help="图片模型名称，默认 gpt-image-2",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="图片生成提示词",
    )
    parser.add_argument(
        "--size",
        default="1024x1024",
        help="图片尺寸；默认 1024x1024，作为当前保守测试尺寸，例如 1024x1024、1536x1024、1024x1536",
    )
    parser.add_argument(
        "--quality",
        default="low",
        help="图片质量参数，默认 low，用于优先验证能否生成",
    )
    parser.add_argument(
        "--output",
        default="",
        help="输出文件路径；未提供时自动写入 bin/tmp/ 下的时间戳文件",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="请求超时秒数，默认 300",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="失败后的额外重试次数，默认 2",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=5.0,
        help="首次重试前等待秒数，后续按指数退避，默认 5",
    )
    return parser.parse_args()


def choose_api_key(arg_value: str) -> str:
    if arg_value:
        return arg_value
    for env_name in ("OPENAI_API_KEY", "ONEAPI_API_KEY", "API_KEY"):
        value = os.environ.get(env_name, "")
        if value:
            return value
    raise SystemExit("未提供 --api-key，且环境变量 OPENAI_API_KEY / ONEAPI_API_KEY / API_KEY 也为空")


def choose_base_url(arg_value: str) -> str:
    if arg_value:
        return arg_value.rstrip("/")
    for env_name in ("OPENAI_BASE_URL", "ONEAPI_BASE_URL", "BASE_URL"):
        value = os.environ.get(env_name, "")
        if value:
            return value.rstrip("/")
    raise SystemExit("未提供 --base-url，且环境变量 OPENAI_BASE_URL / ONEAPI_BASE_URL / BASE_URL 也为空")


def choose_output_path(arg_value: str) -> Path:
    if arg_value:
        return Path(arg_value)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    return Path("bin/tmp") / f"gpt-image-2-{timestamp}.png"


def save_image(image_b64: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = base64.b64decode(image_b64)
    output_path.write_bytes(image_bytes)


def describe_status_error(exc: APIStatusError) -> str:
    status_code = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    if body:
        return f"HTTP {status_code}: {body}"
    return f"HTTP {status_code}: {exc}"


def generate_image_with_retry(client: OpenAI, args: argparse.Namespace):
    total_attempts = args.retries + 1
    delay = max(0.0, args.retry_delay)

    for attempt in range(1, total_attempts + 1):
        if total_attempts > 1:
            print(f"请求尝试 {attempt}/{total_attempts} ...")

        started_at = time.monotonic()
        try:
            response = client.images.generate(
                model=args.model,
                prompt=args.prompt,
                size=args.size,
                quality=args.quality,
                timeout=args.timeout,
            )
            elapsed = time.monotonic() - started_at
            print(f"请求成功，用时 {elapsed:.2f}s")
            return response
        except InternalServerError as exc:
            elapsed = time.monotonic() - started_at
            status_code = getattr(exc, "status_code", None)
            is_524 = status_code == 524
            print(f"请求失败，用时 {elapsed:.2f}s")
            print(describe_status_error(exc))

            if is_524 and attempt < total_attempts:
                wait_seconds = delay * (2 ** (attempt - 1))
                print(f"检测到 524，通常表示 CDN/网关等待上游图片生成超时；{wait_seconds:.1f}s 后自动重试。")
                time.sleep(wait_seconds)
                continue

            if is_524:
                raise SystemExit(
                    "连续收到 524。这个错误通常不是脚本问题，而是站点前的 CDN/网关等待图片生成结果超时。\n"
                    "建议优先检查：\n"
                    "1. 是否经过 CDN/ESA；可先直连源站或未走 CDN 的入口再测一次。\n"
                    "2. 站点对图片生成这类长请求的回源超时是否足够大。\n"
                    "3. 先把 --quality 改成 standard 或把 --size 调小到 1024x1024 复测。"
                )

            raise SystemExit(describe_status_error(exc))
        except (APITimeoutError, APIConnectionError) as exc:
            elapsed = time.monotonic() - started_at
            print(f"请求失败，用时 {elapsed:.2f}s")
            print(f"网络或客户端超时错误: {exc}")
            if attempt < total_attempts:
                wait_seconds = delay * (2 ** (attempt - 1))
                print(f"{wait_seconds:.1f}s 后自动重试。")
                time.sleep(wait_seconds)
                continue
            raise SystemExit(f"请求失败: {exc}")

    raise SystemExit("请求失败，已达到最大重试次数")


def main() -> int:
    args = parse_args()
    api_key = choose_api_key(args.api_key)
    base_url = choose_base_url(args.base_url)
    output_path = choose_output_path(args.output)

    client = OpenAI(api_key=api_key, base_url=base_url, timeout=args.timeout)

    print("开始生成图片...")
    print(f"Base URL: {base_url}")
    print(f"Model: {args.model}")
    print(f"Size: {args.size}")
    print(f"Quality: {args.quality}")
    print(f"Timeout: {args.timeout}s")
    print(f"Output: {output_path}")
    print()
    print("Prompt:")
    print(args.prompt)
    print()

    response = generate_image_with_retry(client, args)

    if not getattr(response, "data", None):
        raise SystemExit("接口返回成功，但 data 为空")

    image_item = response.data[0]
    image_b64 = getattr(image_item, "b64_json", None)
    image_url = getattr(image_item, "url", None)
    revised_prompt = getattr(response, "revised_prompt", None) or getattr(image_item, "revised_prompt", None)

    if image_b64:
        save_image(image_b64, output_path)
        print(f"图片已保存到: {output_path}")
    elif image_url:
        print("接口返回了 URL，而不是 base64：")
        print(image_url)
    else:
        raise SystemExit("接口返回成功，但既没有 b64_json，也没有 url，无法保存图片")

    if revised_prompt:
        print()
        print("Revised Prompt:")
        print(revised_prompt)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        raise SystemExit("用户中断")