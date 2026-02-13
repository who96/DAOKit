from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rag.evaluation import (
    DEFAULT_DATASET_PATH,
    default_backend_ids,
    load_benchmark_dataset,
    run_retrieval_benchmark,
    write_benchmark_artifacts,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run reproducible retrieval benchmark for embedding backend candidates."
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET_PATH),
        help="Path to benchmark dataset JSON.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where benchmark artifacts will be written.",
    )
    parser.add_argument(
        "--backend",
        action="append",
        dest="backends",
        default=[],
        help="Embedding backend id to evaluate. Repeat for multiple candidates.",
    )
    parser.add_argument(
        "--include-optional-api",
        action="store_true",
        help="Include optional API embedding candidates in default backend set.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        action="append",
        dest="top_ks",
        default=[],
        help="Top-k thresholds for metric aggregation. Repeat for multiple values.",
    )
    parser.add_argument(
        "--dimensions",
        type=int,
        default=64,
        help="Embedding vector dimensions for backend evaluation.",
    )
    parser.add_argument("--task-id", default="DKT-061", help="Task id label for artifacts.")
    parser.add_argument("--run-id", default="manual", help="Run id label for artifacts.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    dataset = load_benchmark_dataset(args.dataset)
    backends = tuple(args.backends) or default_backend_ids(
        include_optional_api=args.include_optional_api
    )
    top_ks = tuple(args.top_ks) if args.top_ks else dataset.top_ks

    result = run_retrieval_benchmark(
        dataset=dataset,
        backend_ids=backends,
        top_ks=top_ks,
        dimensions=args.dimensions,
        task_id=args.task_id,
        run_id=args.run_id,
    )
    paths = write_benchmark_artifacts(result=result, output_dir=Path(args.output_dir))

    summary = {
        "task_id": result.task_id,
        "run_id": result.run_id,
        "dataset_id": result.dataset.dataset_id,
        "backend_count": len(result.backend_results),
        "artifacts": {
            "dataset": paths.dataset_path.as_posix(),
            "metrics": paths.metrics_path.as_posix(),
            "report": paths.report_path.as_posix(),
        },
    }
    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
