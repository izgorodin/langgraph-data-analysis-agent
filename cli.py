from __future__ import annotations

import json

import click
from rich.console import Console
from rich.panel import Panel

# Load environment from .env before importing settings
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from src.agent.graph import build_graph
from src.agent.state import AgentState
from src.config import settings

console = Console()


@click.command()
@click.option(
    "--model",
    "model",
    default=settings.model_name,
    help="LLM model name (gemini-1.5-pro)",
)
@click.option("--verbose", is_flag=True, help="Show intermediate states")
@click.argument("question", required=False)
def main(model: str, verbose: bool, question: str | None):
    # Apply model override early so providers read the intended value
    try:
        if model and model != settings.model_name:
            settings.model_name = model
    except Exception:
        pass
    if question is None:
        question = click.prompt("Enter your analysis question", type=str)

    state = AgentState(question=question)
    app = build_graph()

    try:
        for event in app.stream(state):
            for node, s in event.items():
                if verbose:
                    console.rule(f"[bold cyan]{node}")
                    # Ensure payload is a dict and then truncate the string form
                    if not isinstance(s, dict):
                        try:
                            s = s.model_dump()
                        except Exception:
                            s = {"value": str(s)}
                    payload_str = json.dumps(s, ensure_ascii=False)
                    # Print via print_json first, then show a truncated raw preview if extremely long
                    if len(payload_str) <= 6000:
                        console.print_json(payload_str)
                    else:
                        console.print_json(payload_str)
    except Exception as e:
        console.rule("[bold red]Error")
        console.print(Panel.fit(str(e), title="Execution failed"))
        # Non-zero exit code for error visibility and test expectations
        raise click.ClickException(str(e))

    try:
        final = app.invoke(state)
    except Exception as e:
        console.rule("[bold red]Error")
        console.print(Panel.fit(str(e), title="Execution failed"))
        # Non-zero exit code for error visibility and test expectations
        raise click.ClickException(str(e))
    console.rule("[bold green]Insight")
    console.print(Panel.fit(final.report or "No report", title="Agent Report"))


if __name__ == "__main__":
    main()
