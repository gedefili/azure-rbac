"""Flask dashboard server for the Azure RBAC graph tool.

Exposes a REST API consumed by the D3.js front-end and serves the
single-page HTML dashboard.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, render_template, request
from flask_cors import CORS

logger = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"


def create_app(graph_path: str = "graph.json") -> Flask:
    """Application factory.

    Parameters
    ----------
    graph_path:
        Path to the pre-built graph JSON file served to the front-end.
    """
    app = Flask(
        __name__,
        template_folder=str(_TEMPLATE_DIR),
        static_folder=str(_STATIC_DIR),
    )
    CORS(app)

    # ------------------------------------------------------------------
    # In-memory graph cache
    # ------------------------------------------------------------------

    _cache: dict[str, Any] = {}

    def _load_graph() -> dict[str, Any]:
        if "graph" not in _cache:
            path = Path(graph_path)
            if path.exists():
                _cache["graph"] = json.loads(path.read_text(encoding="utf-8"))
                logger.info("Loaded graph from %s", path)
            else:
                _cache["graph"] = {"nodes": [], "links": []}
                logger.warning("Graph file %s not found – serving empty graph.", path)
        return _cache["graph"]  # type: ignore[return-value]

    def _load_findings() -> list[dict[str, Any]]:
        if "findings" not in _cache:
            findings_path = Path(graph_path).with_suffix("").with_suffix(".findings.json")
            if findings_path.exists():
                _cache["findings"] = json.loads(
                    findings_path.read_text(encoding="utf-8")
                )
            else:
                _cache["findings"] = []
        return _cache["findings"]  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    @app.route("/")
    def index() -> str:
        return render_template("index.html")

    @app.route("/api/graph")
    def api_graph() -> Response:
        """Return the full graph JSON."""
        data = _load_graph()
        node_type = request.args.get("node_type")
        if node_type:
            data = {
                "nodes": [n for n in data["nodes"] if n.get("node_type") == node_type],
                "links": data["links"],
            }
        return jsonify(data)

    @app.route("/api/graph/node/<node_id>")
    def api_node_detail(node_id: str) -> Response:
        """Return detail for a single node, including its direct neighbours."""
        data = _load_graph()
        node = next((n for n in data["nodes"] if n["id"] == node_id), None)
        if node is None:
            return jsonify({"error": "Node not found"}), 404  # type: ignore[return-value]

        # Immediate neighbours
        neighbour_ids = set()
        adj_links = []
        for link in data["links"]:
            if link["source"] == node_id or link["target"] == node_id:
                adj_links.append(link)
                neighbour_ids.add(link["source"])
                neighbour_ids.add(link["target"])

        neighbour_nodes = [n for n in data["nodes"] if n["id"] in neighbour_ids]

        return jsonify(
            {
                "node": node,
                "neighbours": neighbour_nodes,
                "links": adj_links,
            }
        )

    @app.route("/api/findings")
    def api_findings() -> Response:
        """Return all security findings."""
        findings = _load_findings()
        severity = request.args.get("severity")
        if severity:
            findings = [f for f in findings if f.get("severity") == severity]
        return jsonify(findings)

    @app.route("/api/findings/summary")
    def api_findings_summary() -> Response:
        """Return finding counts grouped by severity."""
        findings = _load_findings()
        summary: dict[str, int] = {}
        for f in findings:
            s = f.get("severity", "unknown")
            summary[s] = summary.get(s, 0) + 1
        return jsonify(summary)

    @app.route("/api/graph/reload", methods=["POST"])
    def api_reload() -> Response:
        """Clear the in-memory cache so the next request re-reads from disk."""
        _cache.clear()
        return jsonify({"status": "ok"})

    @app.route("/api/health")
    def api_health() -> Response:
        return jsonify({"status": "healthy"})

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("DASHBOARD_PORT", "5000"))
    debug = os.environ.get("DASHBOARD_DEBUG", "false").lower() == "true"
    flask_app = create_app()
    flask_app.run(host="0.0.0.0", port=port, debug=debug)
