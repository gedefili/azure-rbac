# AI Model Selection – Azure AI Foundry

This document evaluates the models available in **Azure AI Foundry** (formerly Azure AI Studio) and recommends which to use for each workload in the Azure RBAC Permission Graph tool.

---

## Workloads and Requirements

| Workload | Input | Output | Key Requirements |
|---|---|---|---|
| **Remediation report** | JSON findings (≤50 findings, ~8 KB) | Markdown report (~2–4 KB) | Reasoning, Azure knowledge, long output |
| **Persona suggestions** | Principal→role mapping (≤500 rows) | Structured list | Pattern matching, categorisation |
| **Executive summary** | Graph stats + findings summary | 2–3 paragraph prose | Concise writing |
| **Interactive Q&A** | User question + graph context | Answer | Low latency, conversational |
| **Batch processing** | Thousands of assignments | Risk scores | Throughput, cost efficiency |

---

## Recommended Models

### 1. GPT-4o (Default Recommendation)

**Use for**: Remediation reports, persona suggestions, executive summaries

| Property | Value |
|---|---|
| Provider | OpenAI (via Azure) |
| Context window | 128 K tokens |
| Max output | 4 096 tokens (default) / 16 K (extended) |
| Multimodal | Yes (text + images) |
| Azure region availability | East US, West Europe, Sweden Central, and others |
| Pricing (as of 2025) | ~$5 / M input tokens, ~$15 / M output tokens |

**Why GPT-4o for this tool**:
- Strong reasoning about complex permission graphs
- Deep knowledge of Azure RBAC, Entra ID, and security best practices
- Reliable structured output (JSON/Markdown) with low hallucination rate
- Available in Azure AI Foundry with Azure AD authentication (no key required)

**Configuration in AI Foundry**:
```json
{
  "deployment_name": "gpt-4o",
  "model": "gpt-4o",
  "capacity": 10,
  "sku": "Standard"
}
```

---

### 2. GPT-4o-mini

**Use for**: Interactive Q&A, low-latency responses, batch risk scoring

| Property | Value |
|---|---|
| Provider | OpenAI (via Azure) |
| Context window | 128 K tokens |
| Max output | 16 K tokens |
| Pricing (as of 2025) | ~$0.15 / M input tokens, ~$0.60 / M output tokens |

**Why GPT-4o-mini**:
- ~30× cheaper than GPT-4o for tasks that don't require deep reasoning
- Fast enough for interactive dashboard Q&A (< 1 s first token)
- Suitable for scoring individual role assignments against a risk rubric

**Recommended usage split**:
- Use GPT-4o for full remediation reports (run once per scan)
- Use GPT-4o-mini for interactive chat and per-node explanations

---

### 3. Phi-4 (Microsoft)

**Use for**: On-premises / air-gapped deployments, cost-sensitive environments

| Property | Value |
|---|---|
| Provider | Microsoft |
| Model size | 14 B parameters |
| Context window | 16 K tokens |
| Deployment | Serverless API or dedicated managed compute |
| Pricing | Serverless: pay-per-token; Managed: compute cost only |

**Why Phi-4**:
- Strong reasoning performance relative to its size
- Can be deployed to a **dedicated endpoint** within your Azure subscription (data never leaves your tenant)
- Lower cost for high-volume batch processing
- Available via Azure AI Foundry Model Catalog

**Limitations**:
- Smaller context window limits the size of the graph that can be analysed in a single call
- Less Azure-specific training data than GPT-4o

---

### 4. Phi-3.5-MoE-instruct (Microsoft)

**Use for**: Cost-optimised batch scoring of individual findings

| Property | Value |
|---|---|
| Provider | Microsoft |
| Architecture | Mixture-of-Experts |
| Context window | 128 K tokens |
| Strengths | Reasoning, coding, instruction following |

---

### 5. Llama 3.3 70B (Meta, via Azure AI Foundry)

**Use for**: Alternative to GPT-4o when open-model licensing is required

| Property | Value |
|---|---|
| Provider | Meta (hosted by Microsoft) |
| Context window | 128 K tokens |
| Deployment | Serverless (pay-per-token) or managed compute |
| License | Meta Llama 3.3 Community License |

---

## Decision Matrix

| Scenario | Recommended Model | Fallback |
|---|---|---|
| Production remediation reports | **GPT-4o** | Llama 3.3 70B |
| Interactive dashboard Q&A | **GPT-4o-mini** | Phi-3.5-MoE |
| Air-gapped / private deployment | **Phi-4** | Phi-3.5-MoE |
| Highest cost-efficiency batch | **GPT-4o-mini** | Phi-4 |
| Compliance (data residency) | **Phi-4 (dedicated)** | GPT-4o (West Europe) |

---

## Prompt Engineering Guidelines

### Remediation report prompt structure

```
SYSTEM: You are an Azure security expert and IAM architect. [detailed instructions]

USER: {
  "findings": [...],          // SecurityAnalyzer output
  "finding_count_by_severity": { "critical": 1, "high": 3, ... },
  "graph_summary": { "node_count": 450, "edge_count": 820 }
}
```

**Recommended parameters**:

| Parameter | Value | Reason |
|---|---|---|
| `temperature` | 0.2–0.3 | Deterministic, factual output |
| `max_tokens` | 4 096 | Enough for comprehensive report |
| `top_p` | 0.95 | Good diversity without randomness |

### Persona suggestion prompt structure

Ask the model to:
1. Group principals by permission overlap (Jaccard similarity of role sets)
2. Name each group after a recognisable job function
3. List the minimum set of built-in or custom roles needed

---

## Token Estimation

| Input type | Approximate tokens |
|---|---|
| Single Finding object (JSON) | ~150–300 tokens |
| 50 findings | ~7 500–15 000 tokens |
| Principal→role map (100 principals) | ~3 000–6 000 tokens |
| Graph summary | ~200–500 tokens |

A full remediation report for a 50-finding scan costs approximately:
- **Input**: ~15 000 tokens → $0.075 with GPT-4o
- **Output**: ~3 000 tokens → $0.045 with GPT-4o
- **Total**: ~$0.12 per full scan

---

## Responsible AI Considerations

1. **Data minimisation**: Send only finding IDs, severity, and description to the model – never raw credential values or sensitive resource names unless necessary.
2. **Output validation**: Parse model output programmatically; do not execute any commands it suggests without human review.
3. **Content filtering**: Enable Azure AI Content Safety filters in AI Foundry to block harmful outputs.
4. **Audit logging**: Enable diagnostic logs on the AI Foundry resource to record all prompts and completions for compliance.

---

## References

- [Azure AI Foundry Model Catalog](https://ai.azure.com/explore/models)
- [GPT-4o deployment guide](https://learn.microsoft.com/en-us/azure/ai-services/openai/how-to/create-resource)
- [Phi-4 model card](https://azure.microsoft.com/en-us/blog/phi-4-microsoft-s-newest-small-language-model-specializing-in-complex-reasoning/)
- [Responsible AI at Microsoft](https://www.microsoft.com/en-us/ai/responsible-ai)
