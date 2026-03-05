"""Azure AI Foundry integration.

Sends security findings and graph summaries to an Azure AI Foundry-hosted
language model (default: GPT-4o) for natural-language remediation plans and
role/persona consolidation recommendations.

Set the following environment variables (or load them from Key Vault first):
  AI_FOUNDRY_ENDPOINT  – Azure AI Foundry project endpoint, e.g.
                          https://<hub>.openai.azure.com/
  AI_FOUNDRY_KEY       – API key (leave blank to use DefaultAzureCredential)
  AI_FOUNDRY_DEPLOYMENT – Deployment name, e.g. gpt-4o
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from azure_rbac.security_analyzer import Finding

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = """
You are an Azure security expert and IAM architect. You will be provided with
a JSON summary of Azure RBAC security findings and role assignment statistics.
Your job is to:
1. Provide a concise executive summary of the security posture.
2. Suggest a prioritised remediation plan for each finding.
3. Recommend a set of 'personas' (job-function groups) that can replace the
   current mix of individual and role assignments.
4. Identify any patterns that could be addressed with custom Azure roles.

Always be specific and actionable. Reference Azure documentation where possible.
Respond in Markdown.
""".strip()


class AIAdvisor:
    """Sends RBAC data to Azure AI Foundry and returns recommendations.

    Usage::

        advisor = AIAdvisor()
        report = advisor.generate_remediation_report(findings, graph_summary)
        print(report)
    """

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
    ) -> None:
        self._endpoint = endpoint or os.environ.get("AI_FOUNDRY_ENDPOINT", "")
        self._api_key = api_key or os.environ.get("AI_FOUNDRY_KEY", "")
        self._deployment = deployment or os.environ.get("AI_FOUNDRY_DEPLOYMENT", "gpt-4o")
        self._client: Any = None

    def _get_client(self) -> Any:
        """Lazily initialise the OpenAI client backed by Azure AI Foundry."""
        if self._client is not None:
            return self._client

        if not self._endpoint:
            raise ValueError(
                "AI_FOUNDRY_ENDPOINT is not set. "
                "Set it in your environment or .env file."
            )

        try:
            from openai import AzureOpenAI

            if self._api_key:
                self._client = AzureOpenAI(
                    azure_endpoint=self._endpoint,
                    api_key=self._api_key,
                    api_version="2024-02-01",
                )
            else:
                # Use Azure AD token via DefaultAzureCredential
                from azure.identity import DefaultAzureCredential, get_bearer_token_provider

                token_provider = get_bearer_token_provider(
                    DefaultAzureCredential(),
                    "https://cognitiveservices.azure.com/.default",
                )
                self._client = AzureOpenAI(
                    azure_endpoint=self._endpoint,
                    azure_ad_token_provider=token_provider,
                    api_version="2024-02-01",
                )
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required. Install it with: pip install openai"
            ) from exc

        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_remediation_report(
        self,
        findings: list[Finding],
        graph_summary: dict[str, Any] | None = None,
        extra_context: str = "",
    ) -> str:
        """Generate a Markdown remediation report using Azure AI Foundry.

        Parameters
        ----------
        findings:
            List of Finding objects from SecurityAnalyzer.
        graph_summary:
            Optional dict with high-level statistics about the graph
            (e.g. node/edge counts, subscription list).
        extra_context:
            Any additional free-text context to include in the prompt.

        Returns
        -------
        str
            Markdown-formatted report.
        """
        payload = self._build_payload(findings, graph_summary, extra_context)
        user_message = json.dumps(payload, indent=2)

        logger.info("Sending %d findings to AI Foundry…", len(findings))
        client = self._get_client()
        response = client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": _DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.3,
            max_tokens=4096,
        )
        content: str = response.choices[0].message.content or ""
        logger.info("AI Foundry response received (%d chars)", len(content))
        return content

    def suggest_personas(
        self,
        principal_role_map: dict[str, list[str]],
    ) -> str:
        """Ask the model to suggest job-function personas based on the role map.

        Parameters
        ----------
        principal_role_map:
            Dict mapping principal display names to their list of assigned role names.

        Returns
        -------
        str
            Markdown list of suggested persona groups.
        """
        prompt = (
            "Based on the following mapping of principals to their Azure roles, "
            "identify clusters of principals with similar permission profiles and "
            "suggest named job-function personas (e.g. 'DevOps Engineer', "
            "'Data Analyst', 'Network Admin'). For each persona, list the "
            "recommended Azure built-in or custom role(s).\n\n"
            f"```json\n{json.dumps(principal_role_map, indent=2)}\n```"
        )
        client = self._get_client()
        response = client.chat.completions.create(
            model=self._deployment,
            messages=[
                {"role": "system", "content": _DEFAULT_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=2048,
        )
        return response.choices[0].message.content or ""

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_payload(
        self,
        findings: list[Finding],
        graph_summary: dict[str, Any] | None,
        extra_context: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "findings": [f.to_dict() for f in findings],
            "finding_count_by_severity": self._count_by_severity(findings),
        }
        if graph_summary:
            payload["graph_summary"] = graph_summary
        if extra_context:
            payload["extra_context"] = extra_context
        return payload

    @staticmethod
    def _count_by_severity(findings: list[Finding]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        return counts
