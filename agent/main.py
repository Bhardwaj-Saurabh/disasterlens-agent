"""Programmatic entry point — runs the DisasterLens agent on a single query.

Useful for backend smoke tests without the React verifier UI. The HITL gate
still applies: while the agent is waiting on `await_verifier`, run
`uv run python -m agent.verifier_cli` in another terminal to approve.

Usage:
    uv run python -m agent.main "Busco a mi nieto Carlos Martínez de 15 años..."
    uv run python -m agent.main --demo   # uses a canned María-looking-for-Carlos query

For the ADK dev UI:
    uv run adk dev --module agent.agent
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import textwrap

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from agent.agent import root_agent

DEMO_QUERY = (
    "Soy María González, 68 años. Busco a mi nieto Carlos Martínez. "
    "Tiene 15 años y estudia en Memorial High School. Llevaba una mochila "
    "verde y su camiseta de fútbol número 10. No habla mucho inglés. "
    "No lo encuentro desde el huracán. Por favor ayúdenme."
)


def _print_event(event) -> None:
    """Pretty-print one ADK event to stdout — keeps the demo trace readable."""
    if event.content and event.content.parts:
        for part in event.content.parts:
            if part.text:
                print(textwrap.indent(part.text, "    "))
            elif part.function_call:
                fc = part.function_call
                args_preview = ", ".join(f"{k}={v!r}"[:60] for k, v in (fc.args or {}).items())
                print(f"    🔧 {fc.name}({args_preview})")
            elif part.function_response:
                fr = part.function_response
                resp = fr.response or {}
                summary = ", ".join(f"{k}={str(v)[:40]}" for k, v in list(resp.items())[:3])
                print(f"    ↩  {fr.name} → {summary}")


async def run_query(query: str) -> None:
    print("=" * 70)
    print(f"SEEKER: {query}")
    print("=" * 70)

    session_service = InMemorySessionService()
    runner = Runner(
        app_name="disasterlens",
        agent=root_agent,
        session_service=session_service,
    )
    session = await session_service.create_session(
        app_name="disasterlens", user_id="cli", session_id="s1"
    )
    user_message = types.Content(role="user", parts=[types.Part(text=query)])

    print("\nAGENT TRACE:")
    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=user_message,
    ):
        _print_event(event)

    print("\n" + "=" * 70)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", help="Seeker query (or --demo)")
    parser.add_argument("--demo", action="store_true",
                        help="Run the canned María→Carlos golden-path query")
    args = parser.parse_args()

    if args.demo:
        query = DEMO_QUERY
    elif args.query:
        query = args.query
    else:
        parser.print_help()
        sys.exit(1)

    asyncio.run(run_query(query))


if __name__ == "__main__":
    main()
