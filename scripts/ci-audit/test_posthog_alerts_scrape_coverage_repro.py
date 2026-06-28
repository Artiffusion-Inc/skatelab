#!/usr/bin/env python
"""Repro: PostHog alerts reference un-scraped jobs/metrics (dead monitoring).

Static, deterministic assertion (no live prometheus). Parses:
  - infra/prometheus/prometheus.yml   scrape_configs job_names
  - infra/prometheus/rules/posthog.yml alert exprs

Asserts that alert exprs referencing `job="X"` labels or metric names have a
corresponding scrape target. Two alerts are DEAD-by-design:

  - PostHogWebDown:  `up{job="posthog_web"} == 0`
      -> references job="posthog_web" which NO scrape_config collects
      -> empty vector -> alert NEVER fires.
  - PostHogWorkerLag: `posthog_celery_queue_length > 10000`
      -> references metric posthog_celery_queue_length; no posthog web/worker/celery
         scrape target exists (only posthog_clickhouse, posthog_kafka)
      -> empty vector -> alert NEVER fires.

RED by design: exits 1 when the dead alerts are confirmed missing coverage.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PROMETHEUS_YML = REPO_ROOT / "infra" / "prometheus" / "prometheus.yml"
POSTHOG_RULES_YML = REPO_ROOT / "infra" / "prometheus" / "rules" / "posthog.yml"

JOB_LABEL_RE = re.compile(r'job="([^"]+)"')
# First bare identifier in the expr is the metric name (before any comparator/arith).
METRIC_NAME_RE = re.compile(r"\b([a-zA-Z_][a-zA-Z0-9_]*)\b")


def load_scrape_job_names() -> list[str]:
    """Return the list of job_name strings defined in prometheus.yml scrape_configs."""
    with PROMETHEUS_YML.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    scrape_configs = data.get("scrape_configs") or []
    job_names: list[str] = []
    for cfg in scrape_configs:
        name = cfg.get("job_name")
        if name:
            job_names.append(str(name))
    return job_names


def load_posthog_alerts() -> list[dict]:
    """Return list of {alert, expr} dicts from the posthog rules file."""
    with POSTHOG_RULES_YML.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    alerts: list[dict] = []
    for group in data.get("groups") or []:
        for rule in group.get("rules") or []:
            if "alert" in rule and "expr" in rule:
                alerts.append({"alert": rule["alert"], "expr": str(rule["expr"])})
    return alerts


def referenced_job_labels(expr: str) -> list[str]:
    return JOB_LABEL_RE.findall(expr)


def referenced_metric_name(expr: str) -> str | None:
    """Return the first identifier in the expr (the metric name), ignoring funcs."""
    # Skip PromQL function names by checking against a known small allowlist is fragile;
    # instead take the first identifier that is not a known aggregator/function keyword.
    keywords = {
        "up",
        "and",
        "or",
        "unless",
        "by",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "offset",
        "bool",
    }
    for m in METRIC_NAME_RE.finditer(expr):
        ident = m.group(1)
        if ident in keywords and ident != "up":
            continue
        # skip comparator/arith operators caught by regex are not identifiers anyway
        return ident
    return None


def posthog_service_scrape_exists(job_names: list[str], service_needles: tuple[str, ...]) -> bool:
    """True if any scrape job name plausibly targets a posthog <service> target.

    Scoped to posthog-prefixed jobs so the SkateLab `gpu-worker` job (unrelated to
    PostHog) does not false-positive on the "worker" needle.
    """
    return any(
        jn.startswith("posthog_") and any(n in jn for n in service_needles) for jn in job_names
    )


def main() -> int:
    job_names = load_scrape_job_names()
    job_set = set(job_names)
    alerts = load_posthog_alerts()

    dead: list[str] = []

    for a in alerts:
        name = a["alert"]
        expr = a["expr"]
        jobs = referenced_job_labels(expr)
        metric = referenced_metric_name(expr)

        if jobs:
            # Alert references job="..." labels -> every referenced job must be scraped.
            missing_jobs = [j for j in jobs if j not in job_set]
            if missing_jobs:
                dead.append(
                    f"{name}: expr `{expr}` references job={jobs} but scraped jobs "
                    f"are {sorted(job_set)} -> missing {missing_jobs} -> empty vector "
                    f"-> alert NEVER fires."
                )
        elif metric:
            # Alert references a bare metric name -> require a plausible scrape target.
            # Heuristic: the metric would have to be emitted by a scraped job. For the
            # posthog celery/web metrics, the job name would contain web/worker/celery.
            if metric.startswith("posthog_") and not posthog_service_scrape_exists(
                job_names, ("web", "worker", "celery")
            ):
                dead.append(
                    f"{name}: expr `{expr}` references metric `{metric}` but no "
                    f"posthog web/worker/celery scrape target exists (scraped jobs: "
                    f"{sorted(job_set)}) -> empty vector -> alert NEVER fires."
                )

    if dead:
        print("RED: PostHog dead alerts reference un-scraped jobs/metrics.")  # noqa: T201
        print(f"Scraped jobs: {', '.join(sorted(job_set))}")  # noqa: T201
        for line in dead:
            print(f"  - {line}")  # noqa: T201
        print(  # noqa: T201
            "Impact: PostHog web service down + worker queue backlog are silently "
            "unmonitored. Dead monitoring — alerts exist but can never fire."
        )
        return 1

    print("GREEN: all PostHog alert exprs reference scraped jobs/metrics.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
