"""Azure RBAC Permission Graph Tool.

This package provides utilities to:
- Collect role assignments, definitions, and principal data from an Azure tenant
- Build a NetworkX graph of the permission structure
- Analyse the graph for security issues
- Generate AI-powered remediation plans via Azure AI Foundry
- Serve an interactive web dashboard
"""

from azure_rbac.graph_builder import GraphBuilder
from azure_rbac.security_analyzer import SecurityAnalyzer

__all__ = ["GraphBuilder", "SecurityAnalyzer"]
__version__ = "0.1.0"
