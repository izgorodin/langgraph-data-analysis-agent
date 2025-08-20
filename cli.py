from __future__ import annotations

import json
import signal

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


class TimeoutError(Exception):
    pass


def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")


@click.command()
@click.option(
    "--model",
    "model",
    default=settings.model_name,
    help="LLM model name (gemini-1.5-pro)",
)
@click.option("--verbose", is_flag=True, help="Show intermediate states")
@click.option("--timeout", default=120, help="Timeout in seconds (default: 120)")
@click.argument("question", required=False)
def main(model: str, verbose: bool, timeout: int, question: str | None):
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

    # Set up timeout
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout)

    final = None
    step_counter = 0
    total_steps = (
        6  # plan, synthesize_sql, validate_sql, execute_sql, analyze_df, report
    )

    try:
        for event in app.stream(state):
            for node, s in event.items():
                step_counter += 1

                # Show progress for non-verbose mode
                if not verbose:
                    console.print(
                        f"[cyan]Step {step_counter}/{total_steps}: {node}[/cyan]",
                        end=" ",
                    )
                    if hasattr(s, "error") and s.error:
                        console.print(f"[red]✗ Error: {s.error[:50]}...[/red]")
                    else:
                        console.print(f"[green]✓[/green]")

                # Always capture the latest state
                if isinstance(s, dict):
                    final = AgentState(**s)
                elif hasattr(s, "model_dump"):
                    final = s

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

        # If no final state captured from stream, invoke once
        if final is None:
            final = app.invoke(state)

    except TimeoutError:
        console.rule("[bold red]Timeout")
        console.print(
            Panel.fit(
                f"Operation timed out after {timeout} seconds",
                title="Execution timeout",
            )
        )
        raise click.ClickException(f"Operation timed out after {timeout} seconds")
    except Exception as e:
        console.rule("[bold red]Error")
        console.print(Panel.fit(str(e), title="Execution failed"))
        # Non-zero exit code for error visibility and test expectations
        raise click.ClickException(str(e))
    finally:
        # Cancel the alarm
        signal.alarm(0)

    console.rule("[bold green]Insight")
    console.print(Panel.fit(final.report or "No report", title="Agent Report"))
    console.print(Panel.fit(final.report or "No report", title="Agent Report"))


if __name__ == "__main__":
    main()
