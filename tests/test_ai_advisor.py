"""Tests for ai_advisor.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from azure_rbac.ai_advisor import AIAdvisor
from azure_rbac.security_analyzer import Finding, Severity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _sample_findings() -> list[Finding]:
    return [
        Finding(
            id="RBAC-001-principal:u1-sub:001",
            severity=Severity.HIGH,
            title="Owner at subscription scope",
            description="Principal has Owner at subscription scope.",
            affected_nodes=["principal:u1", "role:owner", "sub:001"],
            remediation="Reduce scope.",
            references=["https://example.com"],
        ),
        Finding(
            id="RBAC-004-principal:sp1",
            severity=Severity.CRITICAL,
            title="SP with Owner",
            description="Service principal has Owner.",
            affected_nodes=["principal:sp1"],
            remediation="Remove Owner.",
        ),
    ]


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestAIAdvisorInit:
    def test_uses_env_defaults(self):
        with patch.dict("os.environ", {
            "AI_FOUNDRY_ENDPOINT": "https://test.openai.azure.com",
            "AI_FOUNDRY_KEY": "test-key",
            "AI_FOUNDRY_DEPLOYMENT": "gpt-4o-mini",
        }):
            advisor = AIAdvisor()
        assert advisor._endpoint == "https://test.openai.azure.com"
        assert advisor._api_key == "test-key"
        assert advisor._deployment == "gpt-4o-mini"

    def test_explicit_params_override_env(self):
        advisor = AIAdvisor(
            endpoint="https://explicit.openai.azure.com",
            api_key="explicit-key",
            deployment="gpt-35-turbo",
        )
        assert advisor._endpoint == "https://explicit.openai.azure.com"
        assert advisor._api_key == "explicit-key"
        assert advisor._deployment == "gpt-35-turbo"

    def test_default_deployment(self):
        with patch.dict("os.environ", {}, clear=True):
            advisor = AIAdvisor()
        assert advisor._deployment == "gpt-4o"


# ---------------------------------------------------------------------------
# _get_client
# ---------------------------------------------------------------------------


class TestGetClient:
    def test_raises_when_no_endpoint(self):
        advisor = AIAdvisor(endpoint="", api_key="key")
        with pytest.raises(ValueError, match="AI_FOUNDRY_ENDPOINT"):
            advisor._get_client()

    def test_creates_client_with_api_key(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
        )
        with patch("openai.AzureOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            advisor._get_client()
            mock_cls.assert_called_once_with(
                azure_endpoint="https://test.openai.azure.com",
                api_key="test-key",
                api_version="2024-02-01",
            )

    def test_creates_client_with_default_credential(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com",
            api_key="",
        )
        with (
            patch("openai.AzureOpenAI") as mock_cls,
            patch("azure.identity.DefaultAzureCredential"),
            patch("azure.identity.get_bearer_token_provider") as mock_token,
        ):
            mock_cls.return_value = MagicMock()
            mock_token.return_value = lambda: "token"
            advisor._get_client()
            mock_cls.assert_called_once()

    def test_caches_client(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com",
            api_key="test-key",
        )
        with patch("openai.AzureOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            c1 = advisor._get_client()
            c2 = advisor._get_client()
            assert c1 is c2
            mock_cls.assert_called_once()


# ---------------------------------------------------------------------------
# _build_payload / _count_by_severity
# ---------------------------------------------------------------------------


class TestBuildPayload:
    def test_payload_structure(self):
        findings = _sample_findings()
        advisor = AIAdvisor()
        payload = advisor._build_payload(findings, {"node_count": 10}, "extra")
        assert "findings" in payload
        assert len(payload["findings"]) == 2
        assert payload["graph_summary"] == {"node_count": 10}
        assert payload["extra_context"] == "extra"
        assert payload["finding_count_by_severity"] == {"high": 1, "critical": 1}

    def test_payload_without_optional_fields(self):
        advisor = AIAdvisor()
        payload = advisor._build_payload([], None, "")
        assert "graph_summary" not in payload
        assert "extra_context" not in payload
        assert payload["findings"] == []

    def test_count_by_severity(self):
        findings = _sample_findings()
        counts = AIAdvisor._count_by_severity(findings)
        assert counts == {"high": 1, "critical": 1}

    def test_count_by_severity_empty(self):
        assert AIAdvisor._count_by_severity([]) == {}


# ---------------------------------------------------------------------------
# generate_remediation_report
# ---------------------------------------------------------------------------


class TestGenerateRemediationReport:
    def test_returns_model_content(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com", api_key="key"
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "# Remediation Report\nDone."

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        advisor._client = mock_client

        result = advisor.generate_remediation_report(_sample_findings())
        assert "Remediation Report" in result
        mock_client.chat.completions.create.assert_called_once()

    def test_handles_none_content(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com", api_key="key"
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        advisor._client = mock_client

        result = advisor.generate_remediation_report([])
        assert result == ""


# ---------------------------------------------------------------------------
# suggest_personas
# ---------------------------------------------------------------------------


class TestSuggestPersonas:
    def test_suggest_personas_calls_model(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com", api_key="key"
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "## Personas\n- DevOps Engineer"

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        advisor._client = mock_client

        result = advisor.suggest_personas({"alice": ["Owner"], "bob": ["Reader"]})
        assert "Personas" in result

    def test_suggest_personas_handles_none(self):
        advisor = AIAdvisor(
            endpoint="https://test.openai.azure.com", api_key="key"
        )
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = None

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        advisor._client = mock_client

        result = advisor.suggest_personas({})
        assert result == ""
