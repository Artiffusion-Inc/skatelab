"""Vast.ai Serverless PyWorker — bridges FastAPI server with Vast.ai orchestration.

Runs alongside the FastAPI model server (port 8000). The PyWorker:
1. Starts an aiohttp server on WORKER_PORT (default 5000)
2. Monitors the model log file for readiness signals
3. Proxies requests to the model server
4. Reports metrics to Vast.ai
"""

from __future__ import annotations

import os

from vastai.serverless.server.worker import (
    BenchmarkConfig,
    HandlerConfig,
    LogActionConfig,
    Worker,
    WorkerConfig,
)


def main() -> None:
    config = WorkerConfig(
        model_server_url="http://127.0.0.1",
        model_server_port=8000,
        model_log_file=os.environ.get("MODEL_LOG_FILE", "/tmp/skatelab-server.log"),  # noqa: S108
        model_healthcheck_url="/health",
        handlers=[
            HandlerConfig(
                route="/ping",
                allow_parallel_requests=True,
                max_queue_time=10.0,
                benchmark_config=BenchmarkConfig(
                    generator=lambda: {},
                    runs=4,
                    concurrency=5,
                    do_warmup=True,
                ),
                workload_calculator=lambda _: 1.0,
            ),
            HandlerConfig(
                route="/detect",
                allow_parallel_requests=False,
                max_queue_time=600.0,
                workload_calculator=lambda _: 1.0,
            ),
            HandlerConfig(
                route="/process",
                allow_parallel_requests=False,
                max_queue_time=600.0,
                workload_calculator=lambda _: 1.0,
            ),
        ],
        log_action_config=LogActionConfig(
            on_load=["Background init complete"],
            on_error=["Traceback (most recent call last):", "RuntimeError:"],
        ),
    )

    Worker(config).run()


if __name__ == "__main__":
    main()
