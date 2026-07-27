"""Command-line entry point: `living-review run --config review.yaml`.

Wires the v1 pipeline:
  load config -> load prior decisions -> (per source) fetch new records
  -> dedupe against corpus -> train RelevanceRanker on prior decisions
  -> rank new records -> write digest + ASReview re-import file -> update corpus.

STATUS: skeleton. The RelevanceRanker core is implemented and validated
(see eval/); source connectors and the corpus store are done; the digest
renderer and full pipeline wiring are TODO.
"""
from __future__ import annotations

import argparse
import sys

from .config import ReviewConfig


def run(config_path: str) -> int:
    cfg = ReviewConfig.load(config_path)
    print(f"[living-review] loaded config for: {cfg.name}")
    print("  Pipeline not fully wired yet. Implemented: config, classifier core, dedupe,")
    print("  PubMed + Europe PMC connectors, corpus store.")
    print("  TODO before first real run: digest renderer + pipeline wiring.")
    print("  Safety: this tool ranks/flags for human review and never auto-excludes.")
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
