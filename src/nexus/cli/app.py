"""
Nexus CLI launcher.

Minimal Typer app that starts the FastAPI server and opens the browser.
All planning interaction happens in the browser at localhost.
"""

from __future__ import annotations

import webbrowser
from typing import Annotated

import typer
import uvicorn
from rich.console import Console

app = typer.Typer(
    name="nexus",
    help="Local-first multi-agent weekend planning system.",
    add_completion=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    port: Annotated[int, typer.Option("--port", "-p", help="Server port")] = 7820,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Start the Nexus server and open the browser."""
    if ctx.invoked_subcommand is not None:
        return

    _start_server(port=port, debug=debug)


@app.command()
def plan(
    intent: Annotated[
        str, typer.Argument(help="Planning intent, e.g. 'hike with the family Sunday'")
    ],  # noqa: E501
    port: Annotated[int, typer.Option("--port", "-p", help="Server port")] = 7820,
    debug: Annotated[bool, typer.Option("--debug", help="Enable debug logging")] = False,
) -> None:
    """Start Nexus with a pre-loaded planning intent."""
    _start_server(port=port, debug=debug, intent=intent)


def _start_server(port: int, debug: bool, intent: str | None = None) -> None:
    """Launch the FastAPI server and open the browser."""
    import urllib.parse

    url = f"http://127.0.0.1:{port}"
    if intent:
        url = f"{url}/?intent={urllib.parse.quote(intent)}"

    console.print(f"[bold green]Nexus[/bold green] → [link={url}]{url}[/link]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    webbrowser.open(url)

    # Import here so server module doesn't need to be importable at CLI import time
    from nexus.config import NexusConfig
    from nexus.web.server import create_app

    try:
        config = NexusConfig.load()
    except FileNotFoundError:
        # Profile not configured yet — start with defaults so the server can
        # serve the /setup page. Config will be reloaded after setup completes.
        config = NexusConfig()
    if debug:
        config = config.model_copy(update={"debug": True})
    application = create_app(config)
    uvicorn.run(
        application,
        host="127.0.0.1",
        port=port,
        log_level="debug" if debug else "warning",
    )
