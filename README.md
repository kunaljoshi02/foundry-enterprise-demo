# Microsoft Foundry — Enterprise Demo (Insurance)

A **deployed and validated** reference build of Microsoft Foundry Agent Service with a VNet-injected core, an existing Azure API Management gateway, and a separate public Foundry project for the managed-Memory preview that currently does not support VNet integration.

> 📘 **Start here:** [`docs/foundry-enterprise-demo-plan.md`](docs/foundry-enterprise-demo-plan.md) — the full deployment plan, architecture, golden paths, demo runbook and as-built appendices.
>
> 🔭 **Observability & field gotchas:** [`docs/observability-runbook.md`](docs/observability-runbook.md) — why App Insights stays empty, the AMPLS decision, APIM token metrics, endpoint/versioning traps.
>
> 🧪 **Seed the demo data:** [`scripts/seed_rerun.py`](scripts/seed_rerun.py) → transcript in [`docs/demo-seed-transcript.md`](docs/demo-seed-transcript.md).
>
> 🧠 **Managed Memory evidence:** [`docs/memory-demo-verification.md`](docs/memory-demo-verification.md) and [`scripts/provision_memory_demo.py`](scripts/provision_memory_demo.py).
>
> 📊 **Evaluation assets:** the triage agent includes a generated 15-case smoke dataset, `eval.yaml`, and resumable evaluator-generation metadata. The evaluator job exceeded the 30-minute workflow threshold; no evaluation run was started.

---

## What this demonstrates

| Pillar | How |
| --- | --- |
| Agent Service + **VNet injection** | Foundry account with `publicNetworkAccess = Disabled`, delegated agent subnet, private endpoints for every dependency |
| **APIM fronting** | Existing APIM instance serves Foundry as a BYOM model connection (`ai-gateway/gpt-4.1`) with JWT validation and token limits |
| **Multi-agent / A2A** | `claims-intake-triage-agent` orchestrates and calls `coverage-settlement-adjudicator` over A2A JSON-RPC |
| **Tools & toolboxes** | Shared `insurance-tools` toolbox: semantic AI Search, Web Search, Code Interpreter, and five versioned Skills; typed A2A function in the hosted orchestrator |
| **Memory** | Public project `ai-aigw-chat-kj-project`: `underwriter-memory-demo-store` attached to `underwriter-memory-demo`, scoped to the portal-resolved Entra identity (`OID_TID`) |
| **Identity / permissions** | System-assigned managed identities, per-agent instance identities, `Foundry User` for toolbox access, `Search Index Data Reader`, and `Foundry Agent Consumer` for A2A |
| **OBO** | Isolated `underwriting-obo-tools` toolbox and `underwriter-obo-profile` `UserEntraToken` connection; requires an interactive signed-in user and intentionally fails for application identities |
| **Observability** | App Insights + Log Analytics traces and metrics; public ingestion enabled for the demo, with AMPLS documented as the production path |
| **Developer experience** | `azd ai agent` scaffold → provision → deploy, from a Bastion-only jump host |
| **Trust & safety** | Grounding rules, clause citation, fraud escalation, protected-class flagging in agent instructions |

---

## Repository layout

```
docs/
  foundry-enterprise-demo-plan.md   Full plan + as-built inventory + Appendices A–F
infra/
  apim/
    foundry-api-policy.xml                 API-level policy (JWT, token limit, backend, rewrite-uri)
    get-deployment-operation-policy.xml    ⚠️ Mandatory BYOM probe mock — see Appendix A
  bicep/
    demo.bicepparam                        Parameters used against foundry-samples template 19
    get-existing-resources.ps1             Helper for discovering landing-zone resources
agents/
  claims-intake-triage-agent/       Hosted orchestrator (Agent Framework, Python) — calls the adjudicator over A2A
  coverage-settlement-adjudicator/  Hosted specialist (Agent Framework, Python) — exposes responses + a2a
  prompt-agents/                    Prompt agent definitions + memory store config (JSON)
toolbox/
  toolbox-v3.yaml                   Verified Search + Web + Code + Skills toolbox
  underwriting-obo-tools.yaml       Isolated user-token/OBO toolbox
skills/                              Five real Foundry Skills (SKILL.md)
data/policy-wordings.json            36-clause synthetic insurance corpus
scripts/
  build_search_index.py              Create/embed/upload the grounding index
  provision_skills.py                Upload and version Foundry Skills
  deploy_prompt_agents.py            Deploy immutable prompt-agent versions
  provision_memory_demo.py           Provision, seed and verify the public managed-Memory demo
  verify_live_agents.py              Exercise all four deployed agents
```

---

## Agents

| Agent | Kind | Model | Role |
| --- | --- | --- | --- |
| `claims-intake-triage-agent` | Hosted | `gpt-4.1` | Orchestrator — classifies FNOL, extracts entities, flags fraud, routes, and delegates to the hosted adjudicator |
| `coverage-settlement-adjudicator` | Hosted | `gpt-4.1` | Specialist — applies policy wording, computes settlement and excess |
| `policy-coverage-advisor` | Prompt | `ai-gateway/gpt-4.1` (**via APIM**) | Grounded coverage Q&A with clause citation; proves the gateway path |
| `underwriting-risk-summarizer` | Prompt | `gpt-4.1` (direct) | Private-project OBO + Web Search + Code Interpreter |
| `underwriter-memory-demo` | Prompt | `gpt-4.1-mini` (public project) | Native managed Memory preference capture and cross-conversation recall |

**Proven flow:** FNOL → triage agent → `adjudicate_claim` function tool → A2A capability probe → hosted-agent Responses fallback → adjudicator → decision surfaced in the triage response.

**Verified live:** the triage agent loaded `claims-tone` and `regulatory-disclosure`, queried `contoso-policy-wordings`, delegated to the hosted adjudicator, and returned its grounded decision. Foundry currently returns HTTP 200 with JSON-RPC error `HostedAgentNotSupported` when a hosted agent is used as an A2A target, so v9 detects that envelope and retries through the adjudicator's hosted Responses endpoint. The public `underwriter-memory-demo` stored three scoped preferences and recalled their consolidated profile in a new conversation. OBO remains in the private project and requires an interactive signed-in user.

---

## Three fixes worth knowing before you rebuild this

These cost real debugging time. Each is documented in full in the plan appendices.

1. **APIM must implement the deployment-metadata probe** (Appendix A). Foundry validates a BYOM connection with `GET {target}/deployments/{model}` and **no `api-version`**. It must return an *ARM Cognitive Services deployment resource* shape, not an OpenAI-style object. Without it, every call fails with a bare `NotFound`.
2. **A2A HTTP 200 does not mean agent success** (Appendix B): inspect the JSON-RPC body. The current service rejects hosted-agent A2A targets with `HostedAgentNotSupported`; the orchestrator uses the hosted Responses protocol as a controlled fallback. Use a prompt agent when demonstrating native Foundry A2A.
3. **Managed Memory preview does not support VNet integration or BYOM model connections** (Appendix C). This demo therefore uses the existing public `ai-aigw-chat-kj-project` for native Memory while keeping the enterprise claims solution private.

---

## Getting started

1. Read [`docs/foundry-enterprise-demo-plan.md`](docs/foundry-enterprise-demo-plan.md) §5 (deployment phases) and §1A (as-built inventory).
2. Deploy the network-secured base using **template 19** from [microsoft-foundry/foundry-samples](https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/) with `infra/bicep/demo.bicepparam`.
3. Apply the APIM policies in `infra/apim/`.
4. Deploy the hosted agents with `azd provision` + `azd deploy` from a host inside the VNet — see Appendix D for the required `azd` environment variables and the service-principal auth workaround.

### Notes on the agent projects

- `uv.lock` is **not committed** (≈350 KB generated lockfile). Run `uv lock` before the first `azd deploy` — the remote Oryx builder requires it, and without it the build falls back to Poetry and fails with `[tool.poetry] section not found`.
- `.env.example` shows the required variables; real values come from `azd env`.

---

## Security

No credentials are committed. The deployment service principal, jump host password, and any tokens are deliberately excluded. Resource IDs and endpoints for the demo environment are present for reference — treat them as environment-specific and replace them for your own build.
