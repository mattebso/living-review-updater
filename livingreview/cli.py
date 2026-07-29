"""Command-line entry point: `living-review run --config review.yaml`.

Pipeline (see pipeline.py):
  load config -> load prior decisions -> (per source) fetch new records
  -> dedupe against corpus -> train RelevanceRanker on prior decisions
  -> rank new records -> write digest + ASReview re-import RIS -> update corpus.
"""
from __future__ import annotations

import argparse
import sys

from .config import ReviewConfig
from .pipeline import run_update


def run(config_path: str) -> int:
    cfg = ReviewConfig.load(config_path)
    print(f"[living-review] {cfg.name}: starting update run")
    try:
        result = run_update(cfg)
    except Exception as e:  # surface a clean message; stack traces help nobody here
        print(f"[living-review] ERROR: {e}", file=sys.stderr)
        return 1
    for source, n in result.source_counts.items():
        print(f"  {source}: {n} record(s) returned")
    print(f"  {result.n_new_candidates} new candidate(s) after dedupe")
    print(f"  digest: {result.digest_path}")
    if result.reimport_path:
        print(f"  re-import file (RIS, ranked order): {result.reimport_path}")
    print("  Reminder: this tool ranks for human review; it never auto-excludes.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="living-review")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run_p = sub.add_parser("run", help="Run one update pass for a review.")
    run_p.add_argument("--config", required=True, help="Path to review YAML config.")
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return run(args.config)
    return 1


if __name__ == "__main__":
    sys.exit(main())
