#!/usr/bin/env python3
"""Agent 2's canonical, official end-to-end CLI entrypoint.

Usage::

    .venv/bin/python3 scripts/run_agent2_pipeline.py \\
        --input <agent1_view.json> --output <downstream_handoff.json>

``--input`` is a JSON-decoded Agent 1 handoff (shaped exactly like Agent 1's own real
``Agent1CuratedKnowledgeView`` -- see ``app.agent2.handoff.translate``'s own docstring).
``--output`` receives the one canonical downstream handoff dict
(``app.agent2.pipeline.build_canonical_downstream_handoff``,
``AGENT2_DOWNSTREAM_CONTRACT_VERSION``) that Agents 3, 4, and 5 all consume unchanged.

This is also the exact entrypoint the five-agent integration harness invokes for Agent 2 (see
``five-agent-integration-harness/app/harness/runners/run_agent2.py``) -- a thin CLI wrapper
around ``app.agent2.pipeline.run_agent2_pipeline``, never a separate implementation of it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    from app.agent2.pipeline import run_agent2_pipeline

    with open(args.input) as f:
        agent1_view = json.load(f)

    result = run_agent2_pipeline(agent1_view)

    with open(args.output, "w") as f:
        json.dump(result.downstream_handoff, f, indent=2)

    print(f"agent2_contract_version={result.downstream_handoff['contract_version']}")
    print(f"agent2_readiness={result.downstream_handoff['readiness']}")
    print(f"agent2_species_count={len(result.downstream_handoff['species'])}")
    print(f"agent2_reaction_count={len(result.downstream_handoff['reactions'])}")
    print(f"agent2_parameter_count={len(result.downstream_handoff['parameters'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
