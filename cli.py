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
from src.bq import get_last_query_metrics
from src.config import settings

console = Console()


class CLITimeoutError(Exception):
    """Internal timeout error to avoid shadowing built-in TimeoutError."""

    pass


def timeout_handler(signum, frame):
    raise CLITimeoutError("Operation timed out")


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
    final_state_from_stream: dict | None = None
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
                    if hasattr(s, "error") and getattr(s, "error"):
                        console.print(
                            f"[red]✗ Error: {getattr(s, 'error')[:50]}...[/red]"
                        )
                    else:
                        console.print("[green]✓[/green]")

                # For verbose output, pretty-print the payload only; don't coerce to AgentState
                if verbose:
                    try:
                        console.rule(f"[bold cyan]{node}")
                        payload = s
                        if not isinstance(payload, dict):
                            try:
                                payload = payload.model_dump()
                            except Exception:
                                payload = {"value": str(payload)}
                        payload_str = json.dumps(payload, ensure_ascii=False)
                        # Print JSON safely: use print_json only if valid and short; otherwise fallback to plain text
                        if len(payload_str) <= 6000:
                            try:
                                console.print_json(payload_str)
                            except Exception:
                                console.print(payload_str)
                        else:
                            console.print(payload_str[:6000] + "… [truncated]")
                    except Exception:
                        # Ensure one bad payload doesn't crash the CLI
                        console.print(
                            f"[yellow]Warning:[/yellow] failed to render node '{node}' output"
                        )

                # Capture final state from stream to avoid re-running pipeline
                try:
                    if node in ("report", "error_handler"):
                        if isinstance(s, dict):
                            final_state_from_stream = s
                except Exception:
                    pass

        # Prefer the final state captured from the stream; fall back to invoke
        if final is None:
            if final_state_from_stream is not None:
                try:
                    final = AgentState(**final_state_from_stream)
                except Exception:
                    # If reconstruction fails, use raw dict-like access later
                    final = final_state_from_stream  # type: ignore[assignment]
            else:
                final = app.invoke(state)

    except CLITimeoutError as exc:
        console.rule("[bold red]Timeout")
        console.print(
            Panel.fit(
                f"Operation timed out after {timeout} seconds",
                title="Execution timeout",
            )
        )
        raise click.ClickException(
            f"Operation timed out after {timeout} seconds"
        ) from exc
    except Exception as e:
        console.rule("[bold red]Error")
        console.print(Panel.fit(str(e), title="Execution failed"))
        # Non-zero exit code for error visibility and test expectations
        raise click.ClickException(str(e))
    finally:
        # Cancel the alarm
        signal.alarm(0)

    console.rule("[bold green]Insight")
    try:
        report_text = getattr(final, "report", None)
        if not report_text and isinstance(final, dict):
            report_text = final.get("report")  # type: ignore[assignment]
    except Exception:
        report_text = None
    console.print(Panel.fit(report_text or "No report", title="Agent Report"))

    # Print timing summary if available
    try:
        timing_summary = None
        if hasattr(final, "get_timing_summary"):
            timing_summary = final.get_timing_summary()
        elif isinstance(final, dict):
            # Reconstruct minimal object for summary if possible
            fs = AgentState(**final)
            timing_summary = fs.get_timing_summary()
        if timing_summary:
            console.rule("[bold blue]Timing")
            try:
                console.print_json(json.dumps(timing_summary))
            except Exception:
                console.print(timing_summary)
    except Exception:
        pass

    # Print BigQuery metrics if available
    try:
        metrics = get_last_query_metrics()
        if metrics:
            console.rule("[bold magenta]BigQuery Metrics")
            try:
                console.print_json(json.dumps(metrics.model_dump()))
            except Exception:
                console.print(metrics)
    except Exception:
        pass


if __name__ == "__main__":
    main()
