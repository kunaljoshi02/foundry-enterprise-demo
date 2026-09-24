# Microsoft Foundry — Enterprise Demo Deployment Plan & Reference Guide

**Audience:** Customer-facing enterprise demo (insurance vertical)
**Subscription:** `ME-MngEnvMCAP013979-joshikunal-1` (`b55aa044-0dd2-46bf-9ef5-31d5c3dee20c`)
**Region:** Sweden Central (pinned by the existing APIM landing zone)
**Status:** ✅ **CORE SOLUTION DEPLOYED AND VALIDATED.** Infrastructure, 2 hosted agents, 2 prompt agents, Search grounding, five Skills, the shared toolbox, Memory, A2A, APIM and telemetry are live. OBO plumbing is deployed but requires an interactive signed-in user; evaluation/optimizer execution is intentionally pending user approval. See **Section 1A — As-Built Inventory** for the verified boundary.

---

## 1. Executive Summary

This plan stands up a **new, network-isolated Microsoft Foundry account and project** in a dedicated VNet (`10.100.0.0/16`), peered to the existing AI landing-zone VNet (`vnet-ailz-kj`, `192.168.0.0/22`) that hosts the customer's existing API Management instance.

The build is based on **template 19 (`19-private-network-agent-tools`)** as the foundation — because it is the only official template that supports **tools behind the VNet** (MCP, OpenAPI, Azure Functions, A2A, AI Search, Fabric IQ) — with the **APIM private-endpoint + DNS pattern from template 16** layered on top.

**Why not template 16 alone:** template 16 explicitly documents *"This template does not support tools (MCP servers, OpenAPI tools, Azure Functions, A2A) behind the VNet."* Since the demo must showcase tools, toolboxes, MCP, skills and a multi-agent A2A flow, template 19 must be the base.

### Key design decisions (confirmed)

| Decision | Choice | Rationale |
| --- | --- | --- |
| Template base | 19 + APIM PE pattern from 16 | Only path that delivers tools-behind-VNet **and** APIM |
| New VNet address space | `10.100.0.0/16` | Class A is supported in Sweden Central; zero overlap with `192.168.0.0/22` |
| Connectivity to APIM | VNet peering (`vnet-foundry-demo` ↔ `vnet-ailz-kj`) | Customer requirement; keeps the landing zone untouched |
| Jump host | Windows Server 2022 + Azure Bastion, no public IP | Foundry portal needs a browser inside the VNet |
| Identity | System-assigned managed identity | Matches template 19 default; simplest RBAC story |
| BYO dependencies | New Cosmos DB, AI Search, Storage, ACR | Clean, disposable demo blast radius |

---

## 1A. As-Built Inventory (deployed & validated)

Everything below exists in the subscription today and has been smoke-tested.

### 1A.1 Core platform

| Component | As-built name | Notes |
| --- | --- | --- |
| Resource group | `rg-foundry-demo` | Sweden Central |
| VNet | `vnet-foundry-demo` — `10.100.0.0/16` | Peered both ways to `vnet-ailz-kj` |
| Subnets | `agent-subnet` `10.100.0.0/24` (delegated), `pe-subnet` `10.100.1.0/24`, `mcp-subnet` `10.100.2.0/24` (delegated), `AzureBastionSubnet` `10.100.3.0/26`, `jumpbox-subnet` `10.100.3.64/27` | |
| Peering | `foundry-to-ailz` ↔ `ailz-to-foundry` | Connected / FullyInSync |
| Private DNS | 9 × `link-foundry-demo` VNet links added to the existing zones in `rg-ai-landing-zone` | Additive only — landing zone untouched |
| Foundry account | `aifoundrydemo3zbz` | `publicNetworkAccess = Disabled` |
| Foundry project | `insurance3zbz` | Endpoint: `https://aifoundrydemo3zbz.services.ai.azure.com/api/projects/insurance3zbz` |
| Capability hosts | `aifoundrydemo3zbz@aml_aiagentservice` (account), `caphostproj` (project) | Standard Agent Setup |
| BYO dependencies | `aifoundrydemo3zbzcosmosdb`, `aifoundrydemo3zbzsearch`, `aifoundrydemo3zbzstorage`, `acr3zbz` | All behind private endpoints |
| Observability | `law-tracing-3zbz`, `appi-tracing-3zbz`, `ampls-tracing-3zbz` | Azure Monitor Private Link Scope |
| Models | `gpt-4.1` (2025-04-14, GlobalStandard, 50K), `text-embedding-3-small` (v1, GlobalStandard, 50K) | Private project models |
| Jump host | `vm-jump-foundry` (WS2022, D4s_v5, **no public IP**), system MI `71f67867-7dcf-4bfb-b81b-99264a1b9561` | Reached via `bastion-foundry` (Standard) + `pip-bastion-foundry` |
| Deployment SP | `sp-foundry-demo-deploy` — appId `a83d036a-1fda-468a-b1a3-4bc6e5fd164f` | Required for `azd` auth (see Appendix D) |

### 1A.2 APIM integration (existing `apim-ailz-kj`, `rg-ai-landing-zone`)

| Item | Value |
| --- | --- |
| API | `foundry-inference`, path `foundry` |
| Operations | `post-any` / `get-any` / `delete-any` on `/*`, **plus `get-deployment` on `GET /deployments/{deploymentName}`** |
| Policy chain | JWT validation → token-limit → set-backend → `rewrite-uri` |
| Foundry connection | BYOM connection `ai-gateway`, consumed by `policy-coverage-advisor` as model `ai-gateway/gpt-4.1` |

> The `get-deployment` operation is **not optional** — see **Appendix A**.

### 1A.3 Agents

| # | Agent | Kind | Model | Purpose | Status |
| --- | --- | --- | --- | --- | --- |
| 1 | `claims-intake-triage-agent` | Hosted (Agent Framework, Python) | `gpt-4.1` | **Orchestrator.** Search + Skills + Code Interpreter + hosted-agent delegation with explicit A2A error handling. | v9 ✅ |
| 2 | `coverage-settlement-adjudicator` | Hosted (Agent Framework, Python) | `gpt-4.1` | **Specialist.** Search + Skills + Code Interpreter; exposes `responses` and `a2a`. | v6 ✅ |
| 3 | `policy-coverage-advisor` | Prompt | `ai-gateway/gpt-4.1` (**via APIM**) | Semantic Search-grounded coverage Q&A with clause citation. | v10 ✅ |
| 4 | `underwriting-risk-summarizer` | Prompt | `gpt-4.1` (direct) | Private-project OBO MCP + Web Search + Code Interpreter. OBO needs an interactive user. | v5 ⚠️ |
| 5 | `underwriter-memory-demo` | Prompt (public project) | `gpt-4.1-mini` | Native managed Memory preference capture and cross-conversation recall. | v1 ✅ |

**Multi-agent flow (proven end-to-end):** FNOL → `claims-intake-triage-agent` → `adjudicate_claim` function tool → A2A capability probe → hosted Responses fallback when Foundry returns `HostedAgentNotSupported` → `coverage-settlement-adjudicator` → adjudication surfaced in the triage response.

**Instance identities:** triage `d14d6f47-034e-4b74-b154-8e01a5eac3dc`, adjudicator `e6d0a891-2ea7-4831-b434-69410133c4c4`. Both hold **Foundry User** for toolbox resources and **Search Index Data Reader**; triage also holds **Foundry Agent Consumer** for the A2A hop.

### 1A.4 Toolbox, connections and memory

| Asset | As-built | Notes |
| --- | --- | --- |
| Toolbox | `insurance-tools`, **default version 1** (recreated) | `aifoundrydemo3zbzsearch` (`semantic`, top 8), `external-risk-search`, `insurance-calculator`, and five Skill resources |
| OBO toolbox | `underwriting-obo-tools` | Isolates the user-token source so an unavailable entitlement or missing user token cannot break claims tools |
| Search index | `contoso-policy-wordings` | 36 synthetic Home, Motor and Liability clauses; semantic configuration plus 1,536-dimensional vectors |
| Skills | `claims-tone`, `regulatory-disclosure`, `adjudication-rationale`, `underwriting-appetite`, `customer-comms-tone` | Real v1/default Foundry Skills exposed as `skill://.../SKILL.md` resources |
| Agent delegation | typed `adjudicate_claim` hosted-agent function | Checks the JSON-RPC envelope, then uses the hosted Responses endpoint because the current service supports prompt agents—not hosted agents—as native A2A targets |
| OBO connection | `underwriter-obo-profile` | `UserEntraToken` against Agent 365 Me MCP. Provisioned; application-identity invocation is rejected by design |
| Public Memory project | `ai-aigw-chat-kj-project` | Existing public project used because managed Memory preview does not support VNet integration |
| Memory store | `underwriter-memory-demo-store` | Chat model `gpt-4.1-mini`, embedding `text-embedding-3-small`; user profile, chat summary, and procedural memory enabled |
| Memory consumer | `underwriter-memory-demo` via `memory_search_preview`, scope `{{$userId}}` | Verified with portal-resolved Entra scope `b7dbc99c-2583-4c12-a839-e8447010dc79_48640a7a-0e09-4f2d-87c1-d483b3c9519d`: preferences stored and recalled in a new portal-equivalent conversation |

> ⚠️ **Memory is not supported on VNet-integrated projects or BYOM model connections.** The private `insurance3zbz` project keeps its secure architecture and does not host the Memory demo. Native Memory runs in the separate public project.

### 1A.5 Verified capability boundary

| Capability | State | Evidence / boundary |
| --- | --- | --- |
| VNet injection, private endpoints, APIM peering | ✅ Verified | Foundry public access disabled; calls run from the Bastion-only jump host |
| APIM/BYOM model governance | ✅ Verified | Advisor v10 uses `ai-gateway/gpt-4.1`; APIM emits token metrics |
| Search / Foundry IQ grounding | ✅ Verified | `contoso-policy-wordings`; advisor and both hosted agents returned clause-grounded answers |
| Toolbox | ✅ Verified | Live `tools/list`: Search, Web Search, Code Interpreter; live `resources/list`: five Skills |
| Skills | ✅ Verified | Hosted traces include `load_insurance_skill`; returned current `SKILL.md` text |
| Hosted A2A | ✅ Verified | Triage v8 → adjudicator v6 using blocking `message/send` |
| Memory | ✅ Verified (public project) | Three scoped preferences stored and recalled across conversations by `underwriter-memory-demo` |
| OBO | ⚠️ User-context gated | Connection/toolbox/agent wiring exists. Managed-identity test returns `signed-in user required`; use the Foundry portal or an end-user-authenticated client |
| Evaluations / Agent Optimizer | ⏳ Not run | Requires an explicit choice of suite source and approval before generating/running evaluation assets |
| Fabric IQ, private custom MCP, File Search, Guardrails API, routines | ◻ Golden-path extensions | Documented architecture options, not deployed in this demo |

---

## 2. Current Environment — Discovery Findings

These were read live from the subscription and materially shape the plan.

### 2.1 API Management inventory

| Name | RG | Region | SKU | VNet type | Verdict |
| --- | --- | --- | --- | --- | --- |
| `apim-ailz-kj` | `rg-ai-landing-zone` | Sweden Central | StandardV2 | **External** (VNet-integrated) | ✅ **Use this one** |
| `apim-finops-h3mamawlufjc6` | `rg-ai-gateway-finops` | Sweden Central | StandardV2 | None | ❌ Not VNet-integrated |
| `vivid-dawn-2058` | `ai-gateway-vivid-dawn-2058` | East US 2 | AIGateway | None | ❌ Wrong region, not VNet-integrated |

`apim-ailz-kj` details:
- Outbound VNet integration subnet: `vnet-ailz-kj/apim-subnet` (`192.168.0.224/27`)
- Inbound private endpoint: **already exists** — `pe-apim-ailz-kj` in `vnet-ailz-kj/pe-subnet`, status `Approved`
- Gateway URL: `https://apim-ailz-kj.azure-api.net`
- `publicNetworkAccess`: `Enabled` (consider disabling for the demo — see §8)

### 2.2 Existing VNets

| VNet | RG | Space | Note |
| --- | --- | --- | --- |
| `vnet-ailz-kj` | `rg-ai-landing-zone` | `192.168.0.0/22` | APIM lives here. Peering target. |
| `vnet-ailz` | `rg-ai-landing-zone` | `192.168.0.0/22` | ⚠️ **Overlaps** `vnet-ailz-kj` — cannot peer both |

`vnet-ailz-kj` already contains a delegated `agent-subnet` (`192.168.0.0/27`, `Microsoft.App/environments`) that is in use. Template docs state the **delegated agent subnet must be exclusively used by a single Foundry account** — confirming a new VNet is the correct approach.

### 2.3 Private DNS zones — a significant accelerator

A full private DNS zone set already exists in `rg-ai-landing-zone`, each already linked to 2 VNets:

`privatelink.services.ai.azure.com` · `privatelink.openai.azure.com` · `privatelink.cognitiveservices.azure.com` · `privatelink.search.windows.net` · `privatelink.documents.azure.com` · `privatelink.blob.core.windows.net` · `privatelink.azurecr.io` · `privatelink.vaultcore.azure.net` · `privatelink.azure-api.net` · `privatelink.applicationinsights.azure.com` · `privatelink.azconfig.io` · `privatelink.swedencentral.azurecontainerapps.io`

**Reuse these** via the template's `existingDnsZones` parameter rather than creating new zones. Creating duplicates would cause split-brain resolution across the peered VNets.

> **Notable consequence:** because `privatelink.azure-api.net` already exists *and* `pe-apim-ailz-kj` already resolves inside it, once that zone is linked to the new Foundry VNet, **Foundry agents can reach APIM privately over peering without provisioning a second APIM private endpoint.** A second PE in the new VNet is optional (see §5, Phase 4).

### 2.4 Existing Foundry accounts

| Account | RG | Public access |
| --- | --- | --- |
| `aiailzetux` | `rg-ai-landing-zone` | Disabled |
| `aiailz-kjmiqv` | `rg-ai-landing-zone` | Disabled |
| `ai-aigw-chat-kj` | `rg-ai-landing-zone` | Enabled |

The new demo account will be separate, in its own RG, so the existing landing zone is not disturbed.

### 2.5 Model quota — Sweden Central (all unused)

| Model | Limit (TPM units) | Used |
| --- | --- | --- |
| `gpt-5.2` / `gpt-5.2-chat` | 1000 | 0 |
| `gpt-5.1` / `gpt-5.1-chat` | 1000 | 0 |
| `gpt-5` / `gpt-5-mini` | 1000 | 0 |
| `gpt-5-nano` | 5000 | 0 |
| `gpt-4o` | 450 | 0 |
| `gpt-4o-mini` | 2000 | 0 |

✅ Ample headroom. Embedding-model quota must be confirmed separately at deploy time (required for Memory — see §6.3).

---

## 3. Target Architecture

```
┌────────────────────────── Sweden Central ──────────────────────────────┐
│                                                                        │
│  ┌──── rg-ai-landing-zone (EXISTING) ─────┐   ┌─ rg-foundry-demo (NEW) ─┐
│  │  vnet-ailz-kj  192.168.0.0/22          │   │ vnet-foundry-demo       │
│  │                                        │   │ 10.100.0.0/16           │
│  │  ┌──────────────────────────────────┐  │   │                         │
│  │  │ apim-subnet 192.168.0.224/27     │  │   │ ┌─────────────────────┐ │
│  │  │   APIM apim-ailz-kj (StandardV2) │◄─┼─┬─┼─┤ agent-subnet        │ │
│  │  │   outbound VNet integration      │  │ │ │ │ 10.100.0.0/24       │ │
│  │  └──────────────────────────────────┘  │ │ │ │ delegated:          │ │
│  │                                        │ │ │ │ Microsoft.App/envs  │ │
│  │  ┌──────────────────────────────────┐  │ │ │ └─────────────────────┘ │
│  │  │ pe-subnet 192.168.0.32/27        │  │ │ │                         │
│  │  │   pe-apim-ailz-kj  (inbound PE)  │◄─┼─┘ │ ┌─────────────────────┐ │
│  │  └──────────────────────────────────┘  │   │ │ pe-subnet           │ │
│  │                                        │   │ │ 10.100.1.0/24       │ │
│  │  Private DNS zones (SHARED)            │   │ │  PE: Foundry acct   │ │
│  │   privatelink.azure-api.net            │   │ │  PE: AI Search      │ │
│  │   privatelink.services.ai.azure.com    │◄──┼─┤  PE: Cosmos DB      │ │
│  │   privatelink.search.windows.net       │   │ │  PE: Storage (blob) │ │
│  │   privatelink.documents.azure.com      │   │ │  PE: ACR            │ │
│  │   privatelink.blob.core.windows.net    │   │ │  PE: Key Vault      │ │
│  │   privatelink.azurecr.io  ... etc      │   │ └─────────────────────┘ │
│  └────────────────────────────────────────┘   │                         │
│                    ▲                          │ ┌─────────────────────┐ │
│                    │  VNet Peering            │ │ mcp-subnet          │ │
│                    └──────────────────────────┤ │ 10.100.2.0/24       │ │
│                       (bidirectional)         │ │ delegated ACA:      │ │
│                                               │ │  MCP servers        │ │
│                                               │ │  A2A agent endpoints│ │
│                                               │ │  Azure Functions    │ │
│                                               │ └─────────────────────┘ │
│                                               │                         │
│                                               │ ┌─────────────────────┐ │
│                                               │ │ AzureBastionSubnet  │ │
│                                               │ │ 10.100.3.0/26       │ │
│                                               │ ├─────────────────────┤ │
│                                               │ │ jumpbox-subnet      │ │
│                                               │ │ 10.100.3.64/27      │ │
│                                               │ │  Win2022 jump host  │ │
│                                               │ └─────────────────────┘ │
│                                               └─────────────────────────┘
│                                                                        │
│  Foundry account: publicNetworkAccess = Disabled                       │
└────────────────────────────────────────────────────────────────────────┘
```

### Traffic flows

| # | Flow | Path |
| --- | --- | --- |
| 1 | Demo operator → Foundry portal | Browser → Bastion → Win2022 jump host → PE in `pe-subnet` → Foundry |
| 2 | Agent → model inference via AI Gateway | agent-subnet → peering → `pe-apim-ailz-kj` → APIM → backend model |
| 3 | Agent → private MCP / A2A / Functions tool | agent-subnet → mcp-subnet (same VNet) |
| 4 | Agent → knowledge (AI Search, Cosmos, Blob) | agent-subnet → PEs in `pe-subnet` |
| 5 | APIM → Foundry (if fronting Foundry APIs) | apim-subnet → peering → Foundry PE in new `pe-subnet` |

---

## 4. Network Design

### 4.1 Address plan — `10.100.0.0/16`

| Subnet | CIDR | Usable | Delegation | Purpose |
| --- | --- | --- | --- | --- |
| `agent-subnet` | `10.100.0.0/24` | 251 | `Microsoft.App/environments` | Foundry Agent Service compute injection |
| `pe-subnet` | `10.100.1.0/24` | 251 | — | Private endpoints |
| `mcp-subnet` | `10.100.2.0/24` | 251 | `Microsoft.App/environments` | MCP servers, A2A endpoints, Functions |
| `AzureBastionSubnet` | `10.100.3.0/26` | 59 | — | Azure Bastion (name is mandatory, /26 min) |
| `jumpbox-subnet` | `10.100.3.64/27` | 27 | — | Windows Server 2022 jump host |
| *(reserved)* | `10.100.3.96/27` | 27 | — | Future build/DevOps agents |
| *(reserved)* | `10.100.4.0/22` | — | — | Growth |

**Overlap check:** `10.100.0.0/16` vs `192.168.0.0/22` → no overlap. ✅
Also clear of reserved ranges called out in the template docs (`169.254.0.0/16`, `172.30.0.0/16`, `172.31.0.0/16`, `192.0.2.0/24`, `100.100.0.0/17`, etc.).

> ⚠️ **Region gate:** Class A (`10.x`) ranges are only supported in a specific region list. **Sweden Central is on that list** — confirmed against the template 16/19 README limitation notes. If the region ever changes, re-validate before reusing `10.100.0.0/16`.

### 4.2 Peering

Two peering links (peering is not transitive and must be created on both sides):

| Link | Direction | Allow VNet access | Allow forwarded traffic | Gateway transit |
| --- | --- | --- | --- | --- |
| `foundry-to-ailz` | `vnet-foundry-demo` → `vnet-ailz-kj` | Yes | Yes | No |
| `ailz-to-foundry` | `vnet-ailz-kj` → `vnet-foundry-demo` | Yes | Yes | No |

Set gateway transit only if the landing zone later gains a VPN/ExpressRoute gateway that the demo VNet should ride.

### 4.3 DNS strategy — reuse, don't recreate

Link each existing zone in `rg-ai-landing-zone` to `vnet-foundry-demo` (a third VNet link per zone), and pass them to the template so it does not create duplicates:

```bicep
param dnsZonesSubscriptionId = ''   // same subscription
param existingDnsZones = {
  'privatelink.services.ai.azure.com':       'rg-ai-landing-zone'
  'privatelink.openai.azure.com':            'rg-ai-landing-zone'
  'privatelink.cognitiveservices.azure.com': 'rg-ai-landing-zone'
  'privatelink.search.windows.net':          'rg-ai-landing-zone'
  'privatelink.documents.azure.com':         'rg-ai-landing-zone'
  'privatelink.blob.core.windows.net':       'rg-ai-landing-zone'
  'privatelink.azurecr.io':                  'rg-ai-landing-zone'
  'privatelink.vaultcore.azure.net':         'rg-ai-landing-zone'
}
```

New Foundry PE A-records land in the shared zones alongside the existing landing-zone records. Hostnames are account-specific, so there is **no collision** with `aiailzetux` / `aiailz-kjmiqv`.

`privatelink.azure-api.net` must also be linked to `vnet-foundry-demo` so agents resolve APIM to its private IP.

### 4.4 NSGs

| Subnet | Inbound | Outbound |
| --- | --- | --- |
| `agent-subnet` | Deny Internet; allow VNet | Allow VNet + peered `192.168.0.0/22`; allow `AzureCloud` service tags required by Agent Service |
| `pe-subnet` | Allow VNet | Default |
| `mcp-subnet` | Allow from `agent-subnet` only | Allow VNet |
| `jumpbox-subnet` | Allow `3389` **from `AzureBastionSubnet` only** | Allow VNet + HTTPS |
| `AzureBastionSubnet` | Per Bastion requirements (do not over-restrict) | Per Bastion requirements |

> Do not attach a restrictive NSG to the delegated `agent-subnet` without validating against the Agent Service required-egress list first — over-restriction is the most common cause of capability-host provisioning failure.

---

## 5. Deployment Plan

### Phase 0 — Preflight (blocking)

```bash
az account set --subscription b55aa044-0dd2-46bf-9ef5-31d5c3dee20c

# Resource providers
for ns in Microsoft.KeyVault Microsoft.CognitiveServices Microsoft.Storage \
          Microsoft.Search Microsoft.Network Microsoft.App \
          Microsoft.ContainerService Microsoft.ApiManagement Microsoft.DocumentDB; do
  az provider register --namespace $ns
done

# Capacity
az cognitiveservices account list-skus --location swedencentral --kind AIServices -o table
```

Also run the repo's preflight helper:
`infrastructure/infrastructure-setup-bicep/deployment-tools/preflight/`

**Gate checks:**
- [ ] Deploying identity has **Owner**, or **Contributor + User Access Administrator**
- [ ] All providers `Registered`
- [ ] Embedding-model quota confirmed in Sweden Central (needed for Memory)
- [ ] `az deployment group what-if` returns no policy violations

### Phase 1 — Resource group + VNet + peering

```bash
az group create -n rg-foundry-demo -l swedencentral
```

Create `vnet-foundry-demo` (`10.100.0.0/16`) with the six subnets from §4.1, then both peering links from §4.2.

> Create the VNet **before** the Foundry deployment and pass it in via `existingVnetResourceId` + `existing*SubnetResourceId`. Template 19 explicitly recommends this for shared/production VNets so it references subnets as-is instead of issuing subnet PUTs that can overwrite NSGs, route tables and delegations.

### Phase 2 — Link private DNS zones

Add a VNet link from each shared zone in `rg-ai-landing-zone` to `vnet-foundry-demo` (registration disabled — these are resolution-only zones).

### Phase 3 — Deploy Foundry (template 19)

Source: `C:\Users\joshikunal\foundry-samples\infrastructure\infrastructure-setup-bicep\19-private-network-agent-tools\`

Key parameters:

```bicep
param location = 'swedencentral'
param aiServices = 'aifoundrydemo'
param firstProjectName = 'insurance-demo'

param modelName = 'gpt-4.1'
param modelFormat = 'OpenAI'
param modelVersion = '2025-04-14'
param modelSkuName = 'GlobalStandard'
param modelCapacity = 50

param existingVnetResourceId       = '<id>/virtualNetworks/vnet-foundry-demo'
param existingAgentSubnetResourceId = '<vnet>/subnets/agent-subnet'
param existingPeSubnetResourceId    = '<vnet>/subnets/pe-subnet'
param existingMcpSubnetResourceId   = '<vnet>/subnets/mcp-subnet'

param dnsZonesSubscriptionId = ''
param existingDnsZones = { /* see §4.3 */ }

param enableContainerRegistry = true
```

Deploy:

```bash
az deployment group create \
  -g rg-foundry-demo \
  --template-file main.bicep \
  --parameters main.bicepparam
```

Then deploy the **project capability host** only after the account capability host has fully succeeded (the template README is explicit about this ordering).

> ⚠️ **Retry rule:** if deployment fails *after* the capability host step begins, a `legionservicelink` service association stays bound to `agent-subnet`. The reliable recovery is to redeploy with a **new VNet name**, or purge the account + delete the capability host and wait ~20 minutes for the link to clear.

### Phase 4 — APIM integration

Because `privatelink.azure-api.net` is already linked and `pe-apim-ailz-kj` already exists, you have two options:

| Option | What | When to choose |
| --- | --- | --- |
| **4a — Reuse (recommended)** | Link `privatelink.azure-api.net` to `vnet-foundry-demo`; agents reach APIM over peering to the existing PE | Fastest, fewest moving parts, one APIM PE to reason about |
| **4b — Dedicated PE** | Port the APIM PE module from template 16 and create a second PE in `10.100.1.0/24` | If you want the demo VNet independent of the landing zone, or to survive peering removal |

Then, to make APIM the AI Gateway in front of models:
1. Create the APIM `/inference` API with the LLM policy chain (token limit, semantic caching, content safety, load balancing).
2. Grant the APIM managed identity **Cognitive Services User** on the backend Foundry account.
3. Configure `validate-azure-ad-token` with the **project MI application (client) ID**.
4. Create the BYOM connection in Foundry, category `ApiManagement`, with `audience` set to `https://cognitiveservices.azure.com`.

Reference implementation: `16-private-network-standard-agent-apim-setup/extensions/byom-cross-region/`

> **Critical:** a BYOM `<connection>/<model>` reference **only** resolves for gateway-category connections (`ApiManagement` or `ModelGateway`) and **only** from a **prompt agent invoked through the Responses API**. The classic Assistants API fails with `invalid_engine_error: Failed to resolve model info`. Plain `AzureOpenAI`/`CognitiveService` connections are **not** resolvable as `<connection>/<model>`.

### Phase 5 — Jump host + Bastion

- Azure Bastion (Standard) in `AzureBastionSubnet` — Standard tier enables native RDP client and file copy, useful for pushing demo assets.
- Windows Server 2022 VM (`D4s_v5` recommended) in `jumpbox-subnet`, **no public IP**.
- Bootstrap: Azure CLI, `azd`, Python 3.11, VS Code, Edge, Git, Docker (for hosted-agent image builds against the private ACR).
- Validate DNS from the jump host:

```powershell
Resolve-DnsName aifoundrydemo.services.ai.azure.com     # must return 10.100.1.x
Resolve-DnsName apim-ailz-kj.azure-api.net              # must return 192.168.0.3x
```

If either returns a public IP, the private DNS zone link is missing.

### Phase 6 — Post-deployment validation

- [ ] Every PE shows `Approved` + `Succeeded`
- [ ] Foundry account `publicNetworkAccess = Disabled`
- [ ] Project managed identity has required RBAC on Search / Cosmos / Storage / ACR
- [ ] From jump host: Foundry portal loads, playground responds
- [ ] From jump host: agent call through APIM succeeds and appears in APIM analytics
- [ ] Traces land in Application Insights

---

## 6. Capability Showcase — Mapping Every Requested Pillar

| # | Pillar | How it is demonstrated | Where it lives |
| --- | --- | --- | --- |
| 1 | **Agent Service + VNet injection** | Agent Service compute injected into delegated `agent-subnet`; account `publicNetworkAccess=Disabled`; all deps behind PEs | Template 19 |
| 2 | **Tools** | Live: Azure AI Search, Code Interpreter, Web Search, typed function calls. File Search/OpenAPI are golden-path extensions | Prompt + hosted agents |
| 3 | **Toolboxes** | `insurance-tools` shared by hosted agents; OBO isolated in `underwriting-obo-tools` to prevent one failing source poisoning all tools | Foundry toolbox service |
| 4 | **MCP** | Live toolbox MCP endpoints plus Agent 365 `UserEntraToken`; private ACA custom MCP is a golden-path extension | Foundry toolboxes |
| 5 | **Memory** | Managed long-term memory store; agent recalls policyholder preferences and prior claims across sessions. **Requires an embedding deployment** (`text-embedding-3-small`) | Project-owned storage |
| 6 | **Foundry IQ** | Live knowledge grounding over 36 policy clauses via AI Search; Fabric IQ/Work IQ remain optional golden-path extensions | Azure AI Search |
| 7 | **Developer Experience** | `azd ai agent` scaffold → local run → deploy → invoke; VS Code on jump host; CI/CD pipeline; agent versioning | Jump host + `azd` |
| 8 | **Identity** | Account + project system-assigned MI; agents run server-side as the project MI | Entra ID |
| 9 | **Permissions** | Least-privilege RBAC: `Foundry User`, `Cognitive Services User`, `AcrPull`, Search/Cosmos data-plane roles | Azure RBAC |
| 10 | **Auth** | Entra ID only, `disableLocalAuth`; token audience `https://ai.azure.com`; APIM `validate-azure-ad-token` | APIM + Foundry |
| 11 | **OBO** | `UserEntraToken` MCP is wired to the underwriting agent. Requires an interactive end-user token; service identities are rejected by design | Isolated MCP toolbox |
| 12 | **Observability** | App Insights tracing; `customEvents` correlation from eval result → exact response; latency/failure analysis; APIM token metrics | App Insights + APIM |
| 13 | **Skills** | Reusable behavioral guidelines (`claims-tone`, `regulatory-disclosure`) attached to the toolbox, surfaced over MCP `resources/list` as `skill://` URIs, versioned independently of the toolbox | Toolbox `skills[]` |
| 14 | **Evaluations & Optimization** | Planned next step: generate an eval suite from instructions, traces, or `eval.yaml`, then run version comparison / Agent Optimizer after approval | Foundry evaluation workflow |
| 15 | **Trust & Safety** | Live: strict grounding, human-review triggers, regulatory Skills and APIM JWT/token policy. Guardrails API is an extension | Agents + APIM |
| 16 | **Manage & Operate** | Live: immutable versions, traces, metrics and APIM cost controls. Routines/continuous evaluation are extensions | Foundry + APIM |

---

## 7. Golden Architecture Paths

Adapted from the official `golden-path` reference in `foundry-samples`. Both paths converge on identical agent code — only the infrastructure differs.

### Path A — Public (dev/test, fastest onboarding)

| Step | Action | Template |
| --- | --- | --- |
| 1–2 | Foundry account + project | `41-standard-agent-setup` (BYO deps) or `40-basic-agent-setup` |
| 3 | *(N/A)* | — |
| 4–5 | BYOM through gateway — pick a variant below | see table |
| 6 | Create prompt agent, invoke via Responses API | SDK |

**BYOM variants:**

| # | Variant | When | Sample | Auth |
| --- | --- | --- | --- | --- |
| 1 | APIM gateway + Foundry model in another project | You want an AI Gateway you own | `01-connections/public-byom-apim` | Project MI |
| 2 | ModelGateway → another Foundry/AOAI account | Reach another account without your own APIM | `01-connections/model-gateway` | Key / OAuth2 |
| 3 | Third-party provider (e.g. OpenAI) | 3P-hosted model | `01-connections/model-gateway` | Key / OAuth2 |
| 4 | BYOM + BYOG (LiteLLM, Kong, custom) | You already run a non-APIM gateway | `01-connections/model-gateway` | Key / OAuth2 |

### Path B — VNet (this demo; regulated / production)

| Step | Action | Template |
| --- | --- | --- |
| 1+2+3 | Account + project + VNet + PEs + DNS + RBAC + capability host | **`19-private-network-agent-tools`** *(chosen)* — or `15` (no tools behind VNet), `11` (basic) |
| 4+5 | Attach existing private APIM + DNS foundation | `16-...-apim-setup` pattern / `01-connections/apim` |
| 4+5 *(alt)* | Create APIM AI Gateway + cross-region private model | `16/extensions/byom-cross-region` |
| 6 | Create prompt agent, invoke via Responses API | SDK (networking-agnostic) |

### Path selection matrix

|  | Path A (Public) | Path B (VNet) — **this demo** |
| --- | --- | --- |
| Public network access | Enabled | **Disabled** (private endpoints) |
| Setup complexity | Lower | Higher |
| Model traffic on Microsoft backbone | No | **Yes** |
| Tools behind VNet | N/A | ✅ with template 19 |
| Best for | Dev/test, quickest AI Gateway onboarding | Regulated, network-secured production |

### ⚠️ Documented path caveats (call these out honestly in the demo)

1. **Assistants API cannot resolve BYOM models.** Use prompt agent + Responses API.
2. **Direct + third-party model connections are not end-to-end private.** Those calls originate from the managed Agent Service inference plane, not the delegated agent subnet, so the upstream endpoint must be publicly reachable. Project *dependencies* stay network-secured, but that model path is not private. Only the **APIM path** (`byom-cross-region`) is end-to-end private.
3. **No upgrade path** from BYO VNet → Managed VNet. Redeployment required.
4. **All projects in an account share model deployments.** No per-project model isolation.
5. **Cosmos DB is single-region** as deployed; multi-region replication is a manual post-step.
6. **Agent subnet is single-account.** Cannot be shared.

### Golden-path prerequisites checklist for step 6

- [ ] BYOM connection has `audience` set → else `Project identity requires an audience to be specified`
- [ ] APIM MI has `Cognitive Services User` on the backend account
- [ ] APIM `validate-azure-ad-token` uses the **project MI application (client) ID**
- [ ] The referenced backend model deployment exists

---

## 8. Use Cases — Insurance Vertical

| # | Use case | Business value | Pillars exercised |
| --- | --- | --- | --- |
| UC-1 | **FNOL intake & triage** — capture first notice of loss, extract facts, search policy wording, apply communication Skills and delegate over A2A | Cuts intake handling time; consistent data capture | Search, Skills, A2A, Observability |
| UC-2 | **Coverage adjudication** — ground a coverage decision in the actual policy wording + endorsements, produce an auditable rationale | Reduces leakage and wrongful denials; regulator-defensible | Foundry IQ, AI Search, A2A, Guardrails, Evaluations |
| UC-3 | **Policy & coverage advisory** — answer "am I covered for X?" grounded strictly in policy wording through APIM | Deflects contact-centre volume; reduces mis-selling risk | Foundry IQ, AI Search, APIM, Trust & Safety |
| UC-4 | **Underwriting risk triage** — recall underwriter preferences, calculate loss ratio, research external risk, and check user identity before an authority-sensitive recommendation | Faster quote turnaround; consistent appetite application | Memory, OBO, Web Search, Code Interpreter |
| UC-5 | **Fraud signal surfacing** — flag anomalous claim patterns for SIU referral | Loss-ratio improvement | MCP, Functions, Observability |
| UC-6 | **Regulatory & audit evidence** — every decision traceable to prompt, tools, model version, policy clause | Audit and conduct-risk readiness | Observability, Evaluations, Manage & Operate |

---

## 9. Agent Designs

### 9.1 Hosted agents — multi-agent claims solution

Two hosted agents run in the agent subnet and form an **orchestrator + specialist** pattern. The current Foundry service rejects a hosted agent as a native A2A target, so the orchestrator detects that JSON-RPC error and delegates through the specialist's private hosted Responses endpoint. A prompt-agent specialist is the golden path when native A2A itself is the capability being demonstrated.

```
   Claimant / adjuster (via jump host or channel)
                 │
                 ▼
   ┌───────────────────────────────────┐
   │ AGENT 1 — Claims Intake &         │
   │           Triage Orchestrator     │  hosted, agent-subnet
   │  • conversational FNOL capture    │
   │  • document/photo extraction      │
   │  • policy validation              │
   │  • severity + complexity scoring  │
   │  • routing decision               │
   └──────────────┬────────────────────┘
                  │  hosted Responses (private)
                  ▼
   ┌───────────────────────────────────┐
   │ AGENT 2 — Coverage & Settlement   │
   │           Adjudicator             │  hosted, agent-subnet
   │  • clause-level coverage analysis │
   │  • fraud signal check             │
   │  • settlement computation         │
   │  • auditable rationale + citations│
   └──────────────┬────────────────────┘
                  │
                  ▼
     Decision packet + full trace → App Insights
```

#### Agent 1 — `claims-intake-triage-agent` (hosted)

| Aspect | Detail |
| --- | --- |
| Role | Entry point; owns the conversation and the FNOL record |
| Model | `gpt-4.1` direct Foundry deployment |
| Tools | `insurance-tools`: **Azure AI Search**, **Code Interpreter**, **Web Search**; typed `adjudicate_claim` delegation function; `load_insurance_skill` resource loader |
| Skills | `claims-tone` (empathetic, non-committal on liability), `regulatory-disclosure` |
| Guardrails | PII redaction; prohibit statements admitting liability |
| Demo moment | Submit a wet-floor FNOL → Skills + Search → hosted specialist → clause-grounded conditional settlement |

#### Agent 2 — `coverage-settlement-adjudicator` (hosted)

| Aspect | Detail |
| --- | --- |
| Role | Specialist invoked over A2A; never talks to the claimant directly |
| Model | `gpt-4.1` direct Foundry deployment |
| Tools | `insurance-tools`: **Azure AI Search**, **Code Interpreter**, **Web Search**; `load_insurance_skill` |
| Skills | `adjudication-rationale`, `regulatory-disclosure`, `customer-comms-tone` |
| Guardrails | Groundedness enforcement — no coverage claim without a cited clause |
| Demo moment | Returns "Covered — $4,200, less $250 excess", citing **Section 3(b) Accidental Damage**, with the fraud check shown as clean |

**Why this is a genuine multi-agent solution:** separation of duties mirrors the real org (intake vs adjudication), each agent has a distinct tool surface and least-privilege identity, they are versioned and evaluated independently, and the A2A hop is a real network hop you can show in the trace.

### 9.2 Prompt agents — insurance

Model + instructions + tools, no container. These deploy in seconds — ideal for live "build it in front of the customer" moments.

#### Agent 3 — `policy-coverage-advisor` (prompt)

| Aspect | Detail |
| --- | --- |
| Purpose | UC-3 — answers "am I covered for X?" strictly from the customer's own policy |
| Model | `ai-gateway/gpt-4.1` (BYOM via APIM) |
| Tools | **Azure AI Search** (`semantic`, top 8) over `contoso-policy-wordings` |
| Skills | Principles embedded in instructions; no toolbox binding on this APIM/BYOM prompt agent |
| Guardrails | Must refuse to speculate; must cite the clause; content safety on |
| Demo moment | Ask about a **deliberately uncovered** peril — the agent declines cleanly and cites the exclusion rather than hallucinating cover. This is the trust proof point. |

#### Agent 4 — `underwriting-risk-summarizer` (prompt) — **the OBO showcase**

| Aspect | Detail |
| --- | --- |
| Purpose | UC-4 — summarise a submission and recommend appetite |
| Model | `gpt-4.1` direct Foundry deployment |
| Tools | Agent 365 MCP with `UserEntraToken` (OBO), **Web Search**, **Code Interpreter** |
| Skills | `underwriting-appetite` and `regulatory-disclosure` principles in instructions; both Skills also exist in the isolated OBO toolbox |
| Demo moment | Run from the Foundry portal or an end-user-authenticated client. The same call from the jump-host managed identity is rejected with `signed-in user required`, proving the OBO boundary. |

#### Agent 5 — `underwriter-memory-demo` (prompt, public project) — **the Memory showcase**

| Aspect | Detail |
| --- | --- |
| Purpose | Demonstrate native managed Memory without weakening the private claims project |
| Project | `ai-aigw-chat-kj-project` (public) |
| Model | `gpt-4.1-mini`; embeddings via `text-embedding-3-small` |
| Tool | `memory_search_preview` against `underwriter-memory-demo-store`, `update_delay: 1` |
| Scope | Portal-resolved Entra identity `OID_TID`: `b7dbc99c-2583-4c12-a839-e8447010dc79_48640a7a-0e09-4f2d-87c1-d483b3c9519d` |
| Demo moment | Show three stored preferences, open a brand-new conversation, and ask the agent to list the saved preferences |

### 9.3 Shared toolbox and skills

```yaml
# insurance-tools toolbox
description: Enterprise insurance toolbox - policy grounding, skills, web and computation
skills:
  - name: claims-tone
  - name: regulatory-disclosure
  - name: adjudication-rationale
  - name: underwriting-appetite
  - name: customer-comms-tone
tools:
  - type: azure_ai_search
    name: aifoundrydemo3zbzsearch
    azure_ai_search:
      indexes:
        - project_connection_id: aifoundrydemo3zbzsearch
          index_name: contoso-policy-wordings
          query_type: semantic
          top_k: 8
  - type: code_interpreter
    name: insurance-calculator
  - type: web_search
    name: external-risk-search
```

The two hosted agents bind to `insurance-tools`; the advisor uses its prompt-agent Search binding. OBO is kept in `underwriting-obo-tools` so a missing user token cannot break claims tools. Demonstrate immutable toolbox versioning by creating a new version, testing its versioned endpoint, then publishing or rolling back.

---

## 10. Suggested Demo Runbook (~45 min) — as-built

| Time | Segment | Shows |
| --- | --- | --- |
| 0–5 | Architecture walkthrough on the diagram | VNet injection, PEs, peering, APIM, zero public surface |
| 5–8 | Show the project endpoint failing from your laptop, then connect via Bastion → `vm-jump-foundry` and load the same URL | Network isolation is real, not configured-on-paper |
| 8–13 | `azd ai agent` scaffold → `azd provision` → `azd deploy` for a hosted agent | Developer Experience |
| 13–20 | `policy-coverage-advisor` — washing-machine escape-of-water answer with exact clauses, USD 500 excess and USD 5,000 trace-and-access limit. Show its APIM trace. | Foundry IQ, Search, APIM, Trust & Safety |
| 20–28 | FNOL → `claims-intake-triage-agent` → A2A → `coverage-settlement-adjudicator`, end to end | Agent Service, Tools, Toolboxes, A2A multi-agent |
| 28–31 | Switch to public `ai-aigw-chat-kj-project`; open `underwriter-memory-demo` and ask for saved preferences in a new conversation. | **Managed Memory**, user scope, cross-conversation recall |
| 31–34 | Return to private `insurance3zbz`; run `underwriting-risk-summarizer` from an end-user-authenticated client and contrast it with managed-identity rejection. | OBO, Identity, Web, Code Interpreter |
| 33–39 | App Insights trace of the multi-agent run; APIM token-limit metrics and the policy chain | Observability, Manage & Operate |
| 39–45 | If the evaluation suite has been generated and approved, show regression results and an Agent Optimizer candidate; otherwise present this as the next lifecycle step | Evaluations & Optimization |

> Keep **Appendix E** open during the runbook — the caveats land far better volunteered than discovered.

---

## 11. Risks, Gaps & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Template 19 lacks native APIM PE support | APIM integration is a manual delta | Reuse existing `pe-apim-ailz-kj` + DNS link (Option 4a) — lowest effort, already validated |
| Capability-host failure leaves `legionservicelink` on the subnet | Redeploy blocked with "subnet already in use" | Redeploy with a new VNet name, or purge account + delete cap host and wait ~20 min |
| `vnet-ailz` and `vnet-ailz-kj` overlap | Only one can peer | Peer to `vnet-ailz-kj` only (that is where APIM lives) |
| Embedding-model quota unverified | Memory cannot be enabled | Verify + deploy `text-embedding-3-small` in Phase 0 |
| APIM `publicNetworkAccess = Enabled` | Weakens the "fully private" narrative | Disable it, or explicitly frame it as the deliberate external ingress point |
| Shared DNS zones now serve three VNets | Landing-zone blast radius | Additive links only; no record collisions; document the change with the platform team |
| Class A range region restriction | `10.x` invalid outside the supported region list | Sweden Central is supported ✅ — re-validate if region changes |
| Direct/3P model connections not end-to-end private | Contradicts the isolation story if demoed | Demo the **APIM path** only; mention the others as documented alternatives |

---

## 12. Cleanup

Correct teardown order matters — deleting the account first strands the capability host.

1. Delete the **project** capability host
2. Delete the **account** capability host (`deleteCaphost.sh` in the template folder)
3. Delete **and purge** the Foundry account ([purge docs](https://learn.microsoft.com/azure/ai-services/recover-purge-resources))
4. Wait ~20 minutes for subnet unlink
5. Remove both peering links
6. Remove the three VNet links from the shared private DNS zones in `rg-ai-landing-zone`
7. `az group delete -n rg-foundry-demo --yes`

Helper: `infrastructure/infrastructure-setup-bicep/deployment-tools/cleanup/`

---

## 13. Reference Links

| Topic | URL |
| --- | --- |
| Networking options (decision) | https://learn.microsoft.com/azure/foundry/agents/concepts/networking-options |
| Configure private link | https://learn.microsoft.com/azure/foundry/how-to/configure-private-link |
| Agent Service VNet | https://learn.microsoft.com/azure/foundry/agents/how-to/virtual-networks |
| Networking deep dive (subnet/IP) | https://learn.microsoft.com/azure/foundry/agents/concepts/agents-networking-deep-dive |
| Feature limitations | https://learn.microsoft.com/azure/foundry/how-to/configure-private-link#foundry-feature-limitations |
| Hosted agents | https://learn.microsoft.com/azure/ai-foundry/agents/concepts/hosted-agents |
| Region support | https://learn.microsoft.com/azure/foundry/reference/region-support |
| Bicep templates | https://github.com/microsoft-foundry/foundry-samples/tree/main/infrastructure/infrastructure-setup-bicep/ |

---

## 14. Post-Deployment Follow-ups

Original open items, now resolved or decided:

1. ~~Confirm target model~~ → **`gpt-4.1`** deployed and proven with BYOM.
2. ~~Confirm embedding model~~ → **`text-embedding-3-small`** deployed in the public project; backs `underwriter-memory-demo-store`.
3. ~~Option 4a vs 4b~~ → **4a** (reuse existing `pe-apim-ailz-kj` + DNS link).
4. **Open:** set APIM `publicNetworkAccess = Disabled`. Currently `Enabled` — it is the deliberate external ingress point. Decide before a security-sensitive audience.
5. **Open:** add `<client-application-ids>` to the APIM JWT `validate-jwt` policy to pin which app registrations may call the gateway.
6. **Open:** on-prem connectivity (would add gateway transit to the peering design) — not required for this demo.
7. **Optional:** publish an eval suite and run Agent Optimizer against `claims-intake-triage-agent` to make the Evaluations & Optimization segment live rather than narrated.

---

# Appendices — As-Built Golden-Path Guidance

These four appendices capture issues that cost real debugging time. Treat them as the golden path for any repeat build.

## Appendix A — APIM BYOM: the mandatory `get-deployment` probe

**Symptom:** a prompt agent bound to a BYOM connection fails with `NotFound` on every invocation, with no useful error in the Foundry portal.

**Root cause (found via App Insights):** before serving traffic, Foundry validates a BYOM connection by issuing `GET {connection.target}/deployments/{model}` — **with no `api-version` query string**. A gateway that only proxies `/openai/*` returns 404, and Foundry marks the connection unusable.

**Fix:** add an APIM operation `get-deployment` on `GET /deployments/{deploymentName}` whose policy is a `return-response` mock returning an **ARM Cognitive Services deployment resource** shape (`id`, `name`, `type: Microsoft.CognitiveServices/accounts/deployments`, `properties.model.{format,name,version}`, `properties.provisioningState: Succeeded`, `sku`). Do **not** return an OpenAI-style deployment object — the shape matters.

**Golden-path rule:** any gateway fronting Foundry as BYOM must implement the deployment-metadata probe, not just chat/completions.

## Appendix B — A2A target limitation and hosted-agent fallback

An HTTP 200 from the A2A endpoint confirms only that the JSON-RPC request was transported. Always inspect the response body for an `error` member.

The live hosted-to-hosted test returned:

```json
{
  "error": {
    "code": -32099,
    "data": {
      "code": "HostedAgentNotSupported",
      "detail": "Use a prompt agent as the A2A target."
    }
  }
}
```

`claims-intake-triage-agent` v9 handles this explicitly. It first sends blocking `message/send`; when—and only when—the service returns `HostedAgentNotSupported`, it derives the adjudicator's private hosted Responses endpoint, invokes it with the same claim summary, and extracts the final assistant `output_text`. Other JSON-RPC errors are returned without fallback.

**Golden paths:**

1. Use a **prompt agent** as the target when native Foundry A2A is the demo objective.
2. Use the **hosted Responses protocol** for a hosted orchestrator calling a hosted specialist.
3. Keep the JSON-RPC envelope check even when HTTP status is 200, and log protocol, response ID, and terminal status without logging claim content.

## Appendix C — Agent Memory

- **Architecture constraint:** managed Memory preview does not support VNet integration. The native Memory demo therefore runs in the existing public project, not `insurance3zbz`.
- **Path is snake_case:** `POST {project_endpoint}/memory_stores?api-version=2025-11-15-preview`.
- **Preview header is mandatory:** `Foundry-Features: MemoryStores=V1Preview`.
- **Attach to an agent** with `memory_search_preview`, `scope: "{{$userId}}"`, and a short `update_delay` for demos.
- **Per-user header:** pass `x-memory-user-id` on every Responses call. Conversation metadata named `userId` does not set the Memory scope.
- **Scope identity:** when `x-memory-user-id` is omitted, Foundry derives `OID_TID` from the caller's token. For this demo, the portal resolves `joshikunal@joshikun.com` to `b7dbc99c-2583-4c12-a839-e8447010dc79_48640a7a-0e09-4f2d-87c1-d483b3c9519d`.
- **Direct commands:** explicit “Remember…” requests return completed `memory_command_preview_call` items.
- **Verified API:** `POST /memory_stores/{name}:search_memories?api-version=2025-11-15-preview`.
- **Invocation:** the Responses API requires `agent_reference: {type: "agent_reference", name: "<agent>"}`. Both a bare `agent` property and an `agent_reference` without `type` are rejected.
- **Not compatible with BYOM or VNet integration** — see §1A.4.
- **`/openai/v1/...` paths reject `api-version`**; the project-scoped control paths require it. Don't mix them.

## Appendix D — Jump host, `azd` and remote execution

**Connecting:** Azure Bastion → `vm-jump-foundry`, local admin `azureadmin` (password in the session artifacts). The VM has no public IP; the Foundry portal and project endpoint are reachable **only** from here.

**`azd` authentication:** `azd auth login --managed-identity` reports success but the `azure.ai.agents` extension then fails with `not logged in`. **Use a service principal**: `azd auth login --client-id … --client-secret … --tenant-id …`.

**`azd` environment must be fully populated**, or `azd deploy` fails with `infrastructure has not been provisioned` even after a successful `azd provision`. Required variables:

```
AZURE_SUBSCRIPTION_ID          AZURE_TENANT_ID
AZURE_LOCATION                 AZURE_AI_DEPLOYMENTS_LOCATION
AZURE_RESOURCE_GROUP           AZURE_AI_ACCOUNT_NAME
AZURE_AI_PROJECT_NAME          AZURE_AI_PROJECT_ID
USE_EXISTING_AI_PROJECT=true   AZD_AGENT_SKIP_ACR=true
AZD_FOUNDRY_ACR_MODE=none      AZURE_CONTAINER_REGISTRY_NAME / _ENDPOINT
FOUNDRY_PROJECT_ENDPOINT       AZURE_OPENAI_ENDPOINT
```

> The SP credential JSON produced by `az ad sp create-for-rbac` has **no `subscriptionId` field** — set `AZURE_SUBSCRIPTION_ID` explicitly or `azd deploy` fails confusingly.

**Remote build requires `uv.lock`.** Deleting it makes the Oryx builder fall back to Poetry and fail with `[tool.poetry] section not found`. `httpx` and `pydantic` are already transitive dependencies of `agent-framework`, so no manifest change is needed to add the A2A function tool.

**`azd ai toolbox` CLI notes:** `publish <name> <version>` only *promotes* an existing version as default — it does not create one. New versions are created implicitly by `connection add|remove` / `skill add|remove`. `remove --no-prompt` also requires `--force`. There is no `--from-file` on `publish`, and no `azd ai agent logs` — use `azd ai agent monitor --type system --follow`.

**Remote PowerShell (`az vm run-command`) reliability:** keep scripts trivial. Scripts built with here-string interpolation plus regex replacement silently produced no output and no file write. The reliable pattern is: base64-encode each file's content locally, then emit a minimal script that decodes it and calls `[System.IO.File]::WriteAllText(...)`. Always start with `$env:PATH = [Environment]::GetEnvironmentVariable("Path","Machine")`. A hung run-command is cleared with `az vm restart -g rg-foundry-demo -n vm-jump-foundry` and a ~60 s wait.

---

## Appendix E — Honest caveats to state in the demo

1. **Managed Memory is demonstrated in a separate public project.** The private claims project remains VNet-injected and `publicNetworkAccess=Disabled`; native Memory preview cannot currently run there.
2. **APIM itself is currently publicly reachable.** That is the deliberate ingress point; call it out rather than letting the customer find it.
3. **Memory, `memory_search_preview` and the A2A toolbox tool are previews.** The `a2a_preview` async-polling gap (Appendix B) is a live example — show the `blocking: true` workaround as the production pattern.
4. **Shared private DNS zones now serve three VNets.** Links are additive with no record collisions, but the platform team should be told.

---

## Appendix F — Observability: making traces and metrics actually work

> Full detail, KQL, and field gotchas: **[`observability-runbook.md`](./observability-runbook.md)**

Wiring telemetry on a VNet-injected Foundry deployment took four independent fixes.
Any one of them missing leaves App Insights completely empty:

1. **Hosted agents have no OTel wiring by default.** Scaffolded agents ship with no
   `APPLICATIONINSIGHTS_CONNECTION_STRING` and no instrumentation code. Add the env var
   plus `azure-monitor-opentelemetry` and `opentelemetry-instrumentation-httpx`
   (`scripts/patch_obs.py`). The **httpx** instrumentation is what makes the A2A hop
   appear as a dependency span — without it the multi-agent story is invisible.
2. **Set `OTEL_SERVICE_NAME` per agent.** Otherwise every span is
   `cloud_RoleName=unknown_service` and the Application Map collapses into one node.
3. **Grant `Monitoring Metrics Publisher` to the agent *instance* identities.** Blueprint
   identities cannot hold role assignments (`PrincipalTypeNotSupported`).
4. **App Insights `publicNetworkAccessForIngestion` must permit the runtime.** This was
   the real blocker, and it surfaces as a misleading `Forbidden` from the OTel exporter
   that looks exactly like an RBAC failure.

### The AMPLS decision — state this explicitly

For the demo we set `publicNetworkAccessForIngestion: Enabled` on `appi-tracing-3zbz`.
That is a **shortcut**. The production golden path is an **Azure Monitor Private Link
Scope**: AMPLS + private endpoint + private DNS zones for `privatelink.monitor.azure.com`,
`privatelink.oms.opinsights.azure.com`, `privatelink.ods.opinsights.azure.com` and
`privatelink.agentsvc.azure-automation.net`. Say this out loud — a regulated customer will
ask, and "we opened it for the demo, here is how you'd close it" is a far stronger answer
than being caught out.

### FinOps: token metrics are a separate policy

`llm-token-limit` enforces quota but **emits nothing**. Add `llm-emit-token-metric` to the
APIM policy for per-workload token attribution. Metrics land in the **APIM-attached**
App Insights (`appi-ailz-kj`), not the Foundry one.

### Four routing gotchas that cost real time

| Gotcha | Consequence |
|---|---|
| Prompt agents use `/openai/v1/responses` and **reject** `api-version`; hosted agents use `/agents/{name}/endpoint/protocols/openai/responses` and **require** `?api-version=v1` | Wrong endpoint → `400` with unhelpful text |
| Prompt-agent body needs `"type": "agent_reference"` | Bare `400 Bad Request`, no explanation |
| Routing follows `@latest`, not `default_version` — `PATCH default_version` returns `200` and does nothing | Must post a **new version** to change behaviour |
| Memory is unsupported on BYOM/APIM-routed models and VNet-integrated projects | Keep Memory off the private agents; demonstrate it with `underwriter-memory-demo` in the public project |
| `UserEntraToken` OBO rejects managed identity callers | Invoke from the Foundry portal or another end-user-authenticated channel; do not use jump-host MI as the OBO validation path |
| Toolbox Search defaults to `vector_semantic_hybrid` | Set `query_type: semantic` explicitly unless the index has an integrated vectorizer |
| Hosted runtime identities need toolbox RBAC | Grant `Foundry User` at account/project scope and target-specific data roles such as `Search Index Data Reader` |

### Demo data

`scripts/seed_rerun.py` produces the full narrative (memory capture → advisor → FNOL
claims exercising toolbox + A2A → cross-conversation recall). Latest run **ok=12, fail=2**
(transient 500s on two memory retries; those personas were already captured). Transcript:
[`demo-seed-transcript.md`](./demo-seed-transcript.md).
