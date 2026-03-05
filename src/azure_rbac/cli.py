"""Typer CLI entry-point for the azure-rbac tool."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="azure-rbac",
    help="Azure RBAC permission graph tool with AI-powered analysis.",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


@app.command("build")
def build_graph(
    output: Annotated[Path, typer.Option("--output", "-o", help="Output JSON file path")] = Path("graph.json"),
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Discover the full tenant RBAC structure and save as a graph JSON file."""
    _setup_logging(verbose)
    from azure_rbac.azure_client import AzureClient
    from azure_rbac.graph_builder import GraphBuilder

    client = AzureClient()
    builder = GraphBuilder(client)
    builder.build()
    builder.save(output)
    console.print(f"[green]Graph saved to {output}[/green]")


@app.command("analyze")
def analyze_graph(
    graph: Annotated[Path, typer.Option("--graph", "-g", help="Path to graph JSON")] = Path("graph.json"),
    output: Annotated[Optional[Path], typer.Option("--output", "-o")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Run security analysis against a saved graph and print findings."""
    _setup_logging(verbose)
    from azure_rbac.graph_builder import GraphBuilder
    from azure_rbac.security_analyzer import SecurityAnalyzer

    if not graph.exists():
        console.print(f"[red]Graph file not found: {graph}[/red]")
        raise typer.Exit(1)

    builder = GraphBuilder.load(graph)
    analyzer = SecurityAnalyzer(builder.graph)
    findings = analyzer.analyze()

    table = Table(title="Security Findings", show_lines=True)
    table.add_column("Severity", style="bold")
    table.add_column("ID")
    table.add_column("Title")
    for f in findings:
        severity_style = {
            "critical": "red",
            "high": "orange3",
            "medium": "yellow",
            "low": "blue",
            "info": "dim",
        }.get(f.severity.value, "")
        table.add_row(
            f"[{severity_style}]{f.severity.value}[/{severity_style}]",
            f.id,
            f.title,
        )
    console.print(table)

    if output:
        data = [f.to_dict() for f in findings]
        output.write_text(json.dumps(data, indent=2), encoding="utf-8")
        console.print(f"[green]Findings written to {output}[/green]")


@app.command("advise")
def ai_advise(
    findings_file: Annotated[Path, typer.Option("--findings", "-f")] = Path("findings.json"),
    graph: Annotated[Optional[Path], typer.Option("--graph", "-g")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Send findings to Azure AI Foundry and print the remediation report."""
    _setup_logging(verbose)
    from azure_rbac.ai_advisor import AIAdvisor
    from azure_rbac.security_analyzer import Finding, Severity

    if not findings_file.exists():
        console.print(f"[red]Findings file not found: {findings_file}[/red]")
        raise typer.Exit(1)

    raw = json.loads(findings_file.read_text(encoding="utf-8"))
    findings = [
        Finding(
            id=f["id"],
            severity=Severity(f["severity"]),
            title=f["title"],
            description=f["description"],
            affected_nodes=f.get("affected_nodes", []),
            remediation=f.get("remediation", ""),
            references=f.get("references", []),
        )
        for f in raw
    ]

    graph_summary = None
    if graph and graph.exists():
        import json as _json
        from azure_rbac.graph_builder import GraphBuilder
        builder = GraphBuilder.load(graph)
        g = builder.graph
        graph_summary = {
            "node_count": g.number_of_nodes(),
            "edge_count": g.number_of_edges(),
        }

    advisor = AIAdvisor()
    report = advisor.generate_remediation_report(findings, graph_summary)
    console.print(report)


@app.command("dashboard")
def run_dashboard(
    graph: Annotated[Path, typer.Option("--graph", "-g")] = Path("graph.json"),
    port: Annotated[int, typer.Option("--port", "-p")] = 5000,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
) -> None:
    """Start the interactive web dashboard."""
    _setup_logging(verbose)
    from azure_rbac.dashboard.app import create_app

    flask_app = create_app(graph_path=str(graph))
    flask_app.run(host="0.0.0.0", port=port, debug=verbose)


if __name__ == "__main__":
    app()
