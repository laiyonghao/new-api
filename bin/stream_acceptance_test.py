#!/usr/bin/env python3

import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


PROMPTS: Dict[str, str] = {
    "python": (
        "你是一名资深 Python 3.12 工程师。请完整设计并实现一个可用于生产的异步任务调度器，"
        "要求支持延迟任务、周期任务、任务重试、指数退避、优先级队列、取消、优雅停机、"
        "结构化日志、Prometheus 指标、单元测试和集成测试。"
        "请给出：1）目录结构；2）核心实现代码；3）关键类型注解；4）测试代码；"
        "5）性能瓶颈分析；6）如何在 FastAPI 中接入。"
        "回答请尽量详细，代码不要省略。"
    ),
    "cpp": (
        "你是一名资深现代 C++20 架构师。请完整设计并实现一个高性能事件驱动网络框架，"
        "要求支持 reactor 模式、线程池、定时器、协程接口、连接生命周期管理、"
        "背压控制、零拷贝优化、可测试性和 benchmark 方案。"
        "请给出：1）整体架构；2）核心类定义与实现；3）关键模板与 RAII 设计；4）错误处理策略；"
        "5）单元测试；6）与 asio/libuv 的取舍分析。"
        "回答请尽量详细，代码不要省略。"
    ),
}


@dataclass
class StreamMetrics:
    target_name: str
    scenario: str
    run_index: int
    url: str
    status_code: int = 0
    content_type: str = ""
    started_at: float = 0.0
    headers_at: float = 0.0
    first_event_at: float = 0.0
    finished_at: float = 0.0
    event_count: int = 0
    data_line_count: int = 0
    data_bytes: int = 0
    done_seen: bool = False
    gaps: List[float] = field(default_factory=list)
    preview_lines: List[str] = field(default_factory=list)
    error: str = ""
    raw_header_lines: List[str] = field(default_factory=list)

    @property
    def header_delay(self) -> float:
        return max(0.0, self.headers_at - self.started_at)

    @property
    def first_event_delay(self) -> float:
        if self.first_event_at == 0.0:
            return -1.0
        return max(0.0, self.first_event_at - self.started_at)

    @property
    def total_duration(self) -> float:
        if self.finished_at == 0.0:
            return -1.0
        return max(0.0, self.finished_at - self.started_at)

    @property
    def avg_gap(self) -> float:
        if not self.gaps:
            return 0.0
        return sum(self.gaps) / len(self.gaps)

    @property
    def max_gap(self) -> float:
        if not self.gaps:
            return 0.0
        return max(self.gaps)

    def has_good_content_type(self) -> bool:
        return "text/event-stream" in self.content_type.lower()

    def pass_fail(self, first_event_threshold: float, max_gap_threshold: float) -> str:
        if self.error:
            return "FAIL"
        if self.status_code != 200:
            return "FAIL"
        if not self.has_good_content_type():
            return "FAIL"
        if self.first_event_delay < 0:
            return "FAIL"
        if self.first_event_delay > first_event_threshold:
            return "WARN"
        if self.max_gap > max_gap_threshold:
            return "WARN"
        if self.event_count < 8:
            return "WARN"
        return "PASS"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="重复运行的 SSE 验收脚本，检查 text/event-stream、首个事件延迟和分块节奏。"
    )
    parser.add_argument("--base-url", required=True, help="公开入口 Base URL，例如 https://1tok.xhh.club/v1")
    parser.add_argument(
        "--origin-base-url",
        default="",
        help="源站 Base URL，例如 https://1tok-origin.xhh.club/v1；提供后会做同请求对比",
    )
    parser.add_argument("--api-key", default="", help="API Key；未提供时尝试读取 OPENAI_API_KEY 或 ONEAPI_API_KEY")
    parser.add_argument(
        "--origin-secret",
        default="",
        help="访问源站时使用的 X-1tok-Origin-Secret；未提供则尝试读取 ORIGIN_SECRET",
    )
    parser.add_argument("--model", default="claude-opus-4-7", help="要测试的模型名称")
    parser.add_argument(
        "--prompt",
        choices=["python", "cpp", "both"],
        default="python",
        help="内置大回答量提示词集合",
    )
    parser.add_argument("--runs", type=int, default=1, help="每个场景重复次数")
    parser.add_argument("--max-tokens", type=int, default=2400, help="请求里的 max_tokens")
    parser.add_argument("--temperature", type=float, default=0.2, help="请求里的 temperature")
    parser.add_argument("--read-timeout", type=int, default=900, help="单次请求读取超时秒数")
    parser.add_argument(
        "--first-event-threshold",
        type=float,
        default=8.0,
        help="首个 SSE data 事件的期望阈值，超过后标记为 WARN",
    )
    parser.add_argument(
        "--max-gap-threshold",
        type=float,
        default=20.0,
        help="相邻 data 事件最大间隔阈值，超过后标记为 WARN",
    )
    parser.add_argument(
        "--save-dir",
        default="",
        help="可选。保存每次请求的 header 和前几条 data 预览，例如 ./tmp/stream-check",
    )
    return parser.parse_args()


def choose_api_key(arg_value: str) -> str:
    if arg_value:
        return arg_value
    for env_name in ("OPENAI_API_KEY", "ONEAPI_API_KEY", "API_KEY"):
        value = __import__("os").environ.get(env_name, "")
        if value:
            return value
    raise SystemExit("未提供 --api-key，且环境变量 OPENAI_API_KEY / ONEAPI_API_KEY / API_KEY 也为空")


def choose_origin_secret(arg_value: str) -> str:
    if arg_value:
        return arg_value
    return __import__("os").environ.get("ORIGIN_SECRET", "")


def normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def scenario_names(prompt_arg: str) -> List[str]:
    if prompt_arg == "both":
        return ["python", "cpp"]
    return [prompt_arg]


def make_payload(model: str, prompt_name: str, max_tokens: int, temperature: float) -> bytes:
    payload = {
        "model": model,
        "stream": True,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {
                "role": "system",
                "content": "你是一名严谨的资深软件工程师，输出完整，不要刻意简写代码。",
            },
            {"role": "user", "content": PROMPTS[prompt_name]},
        ],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def save_artifacts(save_dir: Path, metrics: StreamMetrics) -> None:
    save_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{metrics.target_name}-{metrics.scenario}-run{metrics.run_index}"
    summary_path = save_dir / f"{prefix}.summary.json"
    summary = {
        "target": metrics.target_name,
        "scenario": metrics.scenario,
        "run": metrics.run_index,
        "url": metrics.url,
        "status_code": metrics.status_code,
        "content_type": metrics.content_type,
        "header_delay": round(metrics.header_delay, 3),
        "first_event_delay": round(metrics.first_event_delay, 3),
        "total_duration": round(metrics.total_duration, 3),
        "event_count": metrics.event_count,
        "data_line_count": metrics.data_line_count,
        "data_bytes": metrics.data_bytes,
        "done_seen": metrics.done_seen,
        "avg_gap": round(metrics.avg_gap, 3),
        "max_gap": round(metrics.max_gap, 3),
        "preview_lines": metrics.preview_lines,
        "error": metrics.error,
        "headers": metrics.raw_header_lines,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_stream_request(
    target_name: str,
    base_url: str,
    api_key: str,
    model: str,
    prompt_name: str,
    run_index: int,
    read_timeout: int,
    origin_secret: str = "",
) -> StreamMetrics:
    url = normalize_base_url(base_url) + "/chat/completions"
    payload = make_payload(model, prompt_name, args.max_tokens, args.temperature)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Cache-Control": "no-cache",
    }
    if origin_secret:
        headers["X-1tok-Origin-Secret"] = origin_secret

    request = urllib.request.Request(url=url, data=payload, headers=headers, method="POST")
    metrics = StreamMetrics(target_name=target_name, scenario=prompt_name, run_index=run_index, url=url)
    metrics.started_at = time.monotonic()

    try:
        context = ssl.create_default_context()
        with urllib.request.urlopen(request, timeout=read_timeout, context=context) as response:
            metrics.headers_at = time.monotonic()
            metrics.status_code = response.getcode()
            metrics.content_type = response.headers.get("Content-Type", "")
            metrics.raw_header_lines = [f"{key}: {value}" for key, value in response.headers.items()]

            last_data_at: Optional[float] = None
            event_line_seen = False
            while True:
                raw_line = response.readline()
                if not raw_line:
                    break

                now = time.monotonic()
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")

                if line.startswith("data:"):
                    payload_text = line[5:].lstrip()
                    metrics.data_line_count += 1
                    metrics.data_bytes += len(payload_text.encode("utf-8"))
                    if metrics.first_event_at == 0.0:
                        metrics.first_event_at = now
                    if last_data_at is not None:
                        metrics.gaps.append(now - last_data_at)
                    last_data_at = now
                    event_line_seen = True
                    if payload_text == "[DONE]":
                        metrics.done_seen = True
                    elif len(metrics.preview_lines) < 5:
                        metrics.preview_lines.append(payload_text[:180])
                elif line == "" and event_line_seen:
                    metrics.event_count += 1
                    event_line_seen = False

            if event_line_seen:
                metrics.event_count += 1
            metrics.finished_at = time.monotonic()
    except urllib.error.HTTPError as exc:
        metrics.finished_at = time.monotonic()
        metrics.status_code = exc.code
        metrics.content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        body = exc.read().decode("utf-8", errors="replace")
        metrics.error = f"HTTPError {exc.code}: {body[:400]}"
    except urllib.error.URLError as exc:
        metrics.finished_at = time.monotonic()
        metrics.error = f"URLError: {exc.reason}"
    except TimeoutError:
        metrics.finished_at = time.monotonic()
        metrics.error = "TimeoutError"
    except Exception as exc:
        metrics.finished_at = time.monotonic()
        metrics.error = f"{type(exc).__name__}: {exc}"

    return metrics


def print_header() -> None:
    print("=" * 88)
    print("SSE 验收测试")
    print("=" * 88)
    print(f"模型: {args.model}")
    print(f"公开入口: {normalize_base_url(args.base_url)}")
    if args.origin_base_url:
        print(f"源站入口: {normalize_base_url(args.origin_base_url)}")
    print(f"场景: {', '.join(scenario_names(args.prompt))}")
    print(f"重复次数: {args.runs}")
    print()


def print_metrics(metrics: StreamMetrics) -> None:
    verdict = metrics.pass_fail(args.first_event_threshold, args.max_gap_threshold)
    print(f"[{verdict}] {metrics.target_name} | {metrics.scenario} | run {metrics.run_index}")
    print(f"  URL: {metrics.url}")
    print(f"  HTTP: {metrics.status_code}")
    print(f"  Content-Type: {metrics.content_type or '(empty)'}")
    print(f"  Header delay: {metrics.header_delay:.3f}s")
    if metrics.first_event_delay >= 0:
        print(f"  First data delay: {metrics.first_event_delay:.3f}s")
    else:
        print("  First data delay: missing")
    print(f"  Total duration: {metrics.total_duration:.3f}s")
    print(f"  Events: {metrics.event_count}, data lines: {metrics.data_line_count}, data bytes: {metrics.data_bytes}")
    print(f"  Avg gap: {metrics.avg_gap:.3f}s, Max gap: {metrics.max_gap:.3f}s")
    print(f"  [DONE]: {'yes' if metrics.done_seen else 'no'}")
    if metrics.preview_lines:
        print("  Preview:")
        for line in metrics.preview_lines:
            print(f"    - {line}")
    if metrics.error:
        print(f"  Error: {metrics.error}")
    print()


def summarize_comparison(public_metrics: List[StreamMetrics], origin_metrics: List[StreamMetrics]) -> None:
    if not public_metrics or not origin_metrics or len(public_metrics) != len(origin_metrics):
        return
    print("对比摘要")
    print("-" * 88)
    for public_item, origin_item in zip(public_metrics, origin_metrics):
        print(f"{public_item.scenario} run {public_item.run_index}")
        if public_item.error or origin_item.error:
            print("  有请求失败，跳过差值比较")
            continue
        print(
            "  First data delta: "
            f"{public_item.first_event_delay - origin_item.first_event_delay:+.3f}s | "
            "Total delta: "
            f"{public_item.total_duration - origin_item.total_duration:+.3f}s | "
            "Max gap delta: "
            f"{public_item.max_gap - origin_item.max_gap:+.3f}s"
        )
    print()


def final_exit_code(metrics_list: List[StreamMetrics]) -> int:
    worst = 0
    for item in metrics_list:
        verdict = item.pass_fail(args.first_event_threshold, args.max_gap_threshold)
        if verdict == "FAIL":
            return 2
        if verdict == "WARN":
            worst = max(worst, 1)
    return worst


args = parse_args()


def main() -> int:
    api_key = choose_api_key(args.api_key)
    origin_secret = choose_origin_secret(args.origin_secret)
    save_dir = Path(args.save_dir) if args.save_dir else None

    print_header()

    public_results: List[StreamMetrics] = []
    origin_results: List[StreamMetrics] = []

    for prompt_name in scenario_names(args.prompt):
        for run_index in range(1, args.runs + 1):
            public_metrics = run_stream_request(
                target_name="public",
                base_url=args.base_url,
                api_key=api_key,
                model=args.model,
                prompt_name=prompt_name,
                run_index=run_index,
                read_timeout=args.read_timeout,
            )
            public_results.append(public_metrics)
            print_metrics(public_metrics)
            if save_dir is not None:
                save_artifacts(save_dir, public_metrics)

            if args.origin_base_url:
                origin_metrics = run_stream_request(
                    target_name="origin",
                    base_url=args.origin_base_url,
                    api_key=api_key,
                    model=args.model,
                    prompt_name=prompt_name,
                    run_index=run_index,
                    read_timeout=args.read_timeout,
                    origin_secret=origin_secret,
                )
                origin_results.append(origin_metrics)
                print_metrics(origin_metrics)
                if save_dir is not None:
                    save_artifacts(save_dir, origin_metrics)

    if origin_results:
        summarize_comparison(public_results, origin_results)

    all_results = public_results + origin_results
    exit_code = final_exit_code(all_results)
    if exit_code == 0:
        print("结论: 当前链路表现正常，SSE 头和分块节奏基本符合预期。")
    elif exit_code == 1:
        print("结论: 当前链路可用，但存在值得关注的延迟或分块抖动，建议对比源站结果继续观察。")
    else:
        print("结论: 当前链路不满足验收条件，优先检查 Content-Type、首个事件延迟和中间层缓冲。")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())