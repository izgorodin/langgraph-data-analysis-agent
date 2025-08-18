from __future__ import annotations
import json
import click
from rich.console import Console
from rich.panel import Panel
from src.agent.state import AgentState
from src.agent.graph import build_graph
from src.config import settings

console = Console()

@click.command()
@click.option("--model", "model", default=settings.model_name, help="LLM model name (gemini-1.5-pro)")
@click.option("--verbose", is_flag=True, help="Show intermediate states")
@click.argument("question", required=False)
def main(model: str, verbose: bool, question: str | None):
    if question is None:
        question = click.prompt("Enter your analysis question", type=str)

    state = AgentState(question=question)
    app = build_graph()

    for event in app.stream(state):
        for node, s in event.items():
            if verbose:
                console.rule(f"[bold cyan]{node}")
                payload = s if isinstance(s, dict) else s.model_dump()
                console.print_json(json.dumps(payload, ensure_ascii=False)[:6000])

    final = app.invoke(state)
    console.rule("[bold green]Insight")
    console.print(Panel.fit(final.report or "No report", title="Agent Report"))

if __name__ == "__main__":
    main()
