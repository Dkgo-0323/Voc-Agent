"""Print call inventory. Never loads .env, starts services or calls providers."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).absolute().parents[1]))

from shared.acceptance.planning import build_plan


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=30)
    parser.add_argument(
        "--chat-model", help="Non-secret proposed model ID; not effective config"
    )
    parser.add_argument("--embedding-model", help="Non-secret proposed model ID")
    args = parser.parse_args()
    try:
        plan = build_plan(
            documents=args.documents,
            chat_model=args.chat_model,
            embedding_model=args.embedding_model,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
