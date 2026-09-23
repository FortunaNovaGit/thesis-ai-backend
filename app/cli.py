from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .agents.runtime import make_agent_runtime
from .config import settings
from .models import BuildAction
from .tools.wordpress import make_wordpress_executor
from .workflow import MultiAgentWorkflow


async def _build(request: str) -> None:
    agents = make_agent_runtime(settings.agent_mode, settings.openai_model)
    wp = make_wordpress_executor(settings)
    workflow = MultiAgentWorkflow(settings, agents, wp, Path("runs"))
    result = await workflow.run(request)
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


async def _check_wordpress() -> None:
    wp = make_wordpress_executor(settings)
    probe = await wp.probe()
    checks: dict[str, object] = {"connection": probe}
    for ability in (
        "thesis-ai-bridge/get-site-info",
        "thesis-ai-bridge/list-pages",
        "thesis-ai-bridge/list-plugins",
    ):
        checks[ability] = await wp.execute(BuildAction(ability=ability, rationale="Connection check"))
    print(json.dumps(checks, ensure_ascii=False, indent=2))


def main() -> None:
    # Backwards compatibility with v0.1: a bare string still means `build`.
    known_commands = {"build", "check-wordpress"}
    if len(sys.argv) > 1 and sys.argv[1] not in known_commands and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "build")

    parser = argparse.ArgumentParser(description="5-agent WordPress thesis prototype v0.4")
    sub = parser.add_subparsers(dest="command", required=True)

    build_parser = sub.add_parser("build", help="Run the five-agent workflow")
    build_parser.add_argument("request", help="Natural-language website request")

    sub.add_parser("check-wordpress", help="Verify Bridge authentication and read-only abilities")

    args = parser.parse_args()
    if args.command == "build":
        asyncio.run(_build(args.request))
    elif args.command == "check-wordpress":
        asyncio.run(_check_wordpress())


if __name__ == "__main__":
    main()
