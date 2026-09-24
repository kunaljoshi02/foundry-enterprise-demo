# Observability Runbook & Field Gotchas

Companion to `foundry-enterprise-demo-plan.md`. Everything here was discovered while
making traces, metrics and memory actually work end-to-end on the VNet-injected demo.

---

## 1. What "working" looks like

Foundry App Insights (`appi-tracing-3zbz`, appId `9fa9d000-16e8-4137-83b7-51b488abcd75`)
after a full seed run:

| Table | Rows |
|---|---|
| `dependencies` | 326 |
| `requests` | 14 |
| `traces` | 1716 |
| `customMetrics` | 180 |
| `exceptions` | 12 (benign — see §6) |

APIM App Insights (`appi-ailz-kj`) after the token-metric policy was added:

| Metric | Dimensions |
|---|---|
| `Total Tokens` / `Prompt Tokens` / `Completion Tokens` | `Workload=foundry-insurance-demo`, `API`, `Operation`, `User` |

### The span shape to demo

A single FNOL call to `claims-intake-triage-agent` produces a nested tree:

```
invoke_agent <id>                                  (triage, InProc)
├── POST .../toolboxes/insurance-tools/versions/2/mcp   toolbox handshake
├── tools/list                                          toolbox discovery
├── execute_tool adjudicate_claim                  (InProc)
│   └── POST .../agents/coverage-settlement-adjudicator/endpoint/protocols/a2a
│       └── JSON-RPC HostedAgentNotSupported
│   └── POST .../agents/coverage-settlement-adjudicator/endpoint/protocols/openai/responses
│       └── invoke_agent <id>                      (adjudicator, separate role)
├── chat gpt-4.1                                   (InProc)
└── GET/PUT .../storage/state_stores/...           conversation persistence
```

Prompt-agent spans appear under `cloud_RoleName=responsesapi`:

- `invoke_agent underwriting-risk-summarizer:2` + `execute_tool remote_functions.memory_command` — the Memory tool firing
- `invoke_agent policy-coverage-advisor:3` + `chat ai-gateway/gpt-4.1` — the APIM/BYOM path

That single screenshot proves toolbox, A2A multi-agent, memory, and the APIM gateway
in one view. It is the strongest single visual in the demo.

---

## 2. Gotcha: App Insights private ingestion silently blocks all telemetry

**Symptom.** Agents run fine, `appinsights_configured=True` in container logs, but every
App Insights table returns 0 rows. Container logs repeat:

```
ERROR azure.monitor.opentelemetry.exporter: Retryable server side error:
Operation returned an invalid status 'Forbidden'
```

**The trap.** `Forbidden` reads like an RBAC problem and sends you down a long
role-assignment rabbit hole. It is not (only) RBAC.

**Root cause.** The App Insights component had:

```
publicNetworkAccessForIngestion: "Disabled"
```

The Foundry agent runtime's telemetry egress is not covered by an Azure Monitor Private
Link Scope, so ingestion is rejected at the network layer and surfaced as `Forbidden`.

**Demo fix (what we did):**

```bash
# management-plane PUT setting publicNetworkAccessForIngestion = Enabled
az rest --method get --url "<component-id>?api-version=2020-02-02"   # confirm current
# then PUT the component back with publicNetworkAccessForIngestion: "Enabled"
```

Verify **both** the component *and* the backing Log Analytics workspace
(`law-tracing-3zbz`) are `Enabled` — either one can block ingestion.

**Production golden path (state this in the demo):** use an **Azure Monitor Private Link
Scope (AMPLS)** instead — AMPLS + private endpoint + private DNS zones for
`privatelink.monitor.azure.com`, `privatelink.oms.opinsights.azure.com`,
`privatelink.ods.opinsights.azure.com`, `privatelink.agentsvc.azure-automation.net`.
Public ingestion is a **demo shortcut**, not a recommendation.

---

## 3. Gotcha: RBAC is necessary but not sufficient

Both agent **instance** identities need `Monitoring Metrics Publisher` on the App
Insights resource:

| Agent | Instance principal ID |
|---|---|
| `claims-intake-triage-agent` | `d14d6f47-034e-4b74-b154-8e01a5eac3dc` |
| `coverage-settlement-adjudicator` | `e6d0a891-2ea7-4831-b434-69410133c4c4` |

Assign to the **instance identity**, never the blueprint. Blueprint principals reject
role assignments with:

```
PrincipalTypeNotSupported ... #microsoft.graph.agentIdentityBlueprintPrincipal
```

---

## 4. Gotcha: hosted agents need explicit OTel wiring

Scaffolded hosted agents ship with **no** `APPLICATIONINSIGHTS_CONNECTION_STRING` and no
OTel code. Required changes (applied by `scripts/patch_obs.py`):

1. `azure.yaml` — add to the service `env:` block:
   ```yaml
   APPLICATIONINSIGHTS_CONNECTION_STRING: ${APPLICATIONINSIGHTS_CONNECTION_STRING}
   OTEL_SERVICE_NAME: <agent-name>
   ```
   then `azd env set APPLICATIONINSIGHTS_CONNECTION_STRING "<conn-string>"`.
2. `pyproject.toml` — add `azure-monitor-opentelemetry` and
   `opentelemetry-instrumentation-httpx`.
3. `main.py` — configure Azure Monitor and instrument `httpx` so the **A2A hop shows up
   as a dependency span**. Without httpx instrumentation the multi-agent call is invisible.

**Set `OTEL_SERVICE_NAME`.** Without it every span lands as
`cloud_RoleName=unknown_service` and the Application Map is a single meaningless blob.
With it you get two clean nodes and a visible A2A edge.

---

## 5. Gotcha: APIM token metrics need an explicit policy

`llm-token-limit` (governance) does **not** emit metrics. For the FinOps/chargeback
story you must also add `llm-emit-token-metric` — see `infra/apim/foundry-api-policy.xml`:

```xml
<llm-emit-token-metric namespace="genai">
  <dimension name="API" value="@(context.Api.Name)" />
  <dimension name="Operation" value="@(context.Operation.Name)" />
  <dimension name="User" value="@(context.Request.Headers.GetValueOrDefault("x-user-id","anonymous"))" />
  <dimension name="Workload" value="foundry-insurance-demo" />
</llm-emit-token-metric>
```

These land in the **APIM-attached** App Insights (`appi-ailz-kj`) as `customMetrics`,
**not** in the Foundry App Insights and **not** as a platform metric namespace.
Query them with:

```kusto
customMetrics
| where name == 'Total Tokens'
| extend Workload = tostring(customDimensions.Workload)
| project timestamp, valueSum, Workload
```

---

## 6. Benign noise to pre-empt in the demo

12 `exceptions` rows, all:

```
requests.exceptions.ConnectionError:
HTTPConnectionPool(host='169.254.169.254', port=80) ... /metadata/instance/compute
```

This is the Azure Monitor SDK probing IMDS for VM metadata inside a container where IMDS
isn't reachable. It is harmless and unrelated to agent logic. Call it out before a sharp
customer spots it.

---

## 7. Gotcha: two responses endpoints with *opposite* api-version rules

| Agent type | URL | `api-version` |
|---|---|---|
| Prompt | `POST {EP}/openai/v1/responses` (body carries `agent_reference`) | **must be omitted** — otherwise `api-version query parameter is not allowed when using /v1 path` |
| Hosted | `POST {EP}/agents/{name}/endpoint/protocols/openai/responses` | **required**: `?api-version=v1`, else `400 Missing required query parameter` |

The prompt-agent body must also include the discriminator:

```json
{"agent_reference": {"type": "agent_reference", "name": "policy-coverage-advisor"}, "input": "..."}
```

Omitting `"type"` returns a bare `400 Bad Request` with no explanation.

---

## 8. Gotcha: version routing uses `@latest`, not `default_version`

`version_selection_rules` is:

```json
[{"type": "FixedRatio", "agent_version": "@latest", "traffic_percentage": 100}]
```

`PATCH /agents/{name} {"default_version": N}` returns `200` but **changes nothing** about
what actually serves traffic. To roll back or change behaviour you must **post a new
version**. This is how `policy-coverage-advisor` v3 was created — by re-posting the v1
definition so `@latest` resolved to a BYOM-compatible version.

---

## 9. Gotcha: Memory is unsupported on BYOM connections

Attaching `memory_search_preview` to an agent whose model routes through APIM fails:

```
The following tools are not supported with BYO model: memory_search
```

Consequence for this demo: `policy-coverage-advisor` (routes via `ai-gateway/gpt-4.1`)
**cannot** carry memory. Memory lives only on `underwriting-risk-summarizer`, which uses
the direct `gpt-4.1` deployment. Plan the narrative accordingly — do not promise memory
on the gateway-routed agent.

---

## 10. Gotcha: memory store REST surface is largely undocumented

Working today:

- `GET {EP}/memory_stores?api-version=v1` — list
- `GET {EP}/memory_stores/insurance-memory?api-version=v1` — get **by name** (the id 404s)
- `POST {EP}/memory_stores/{name}/items?api-version=v1` — create

Every search/enumerate variant tried returned 404 or `memory_id is invalid`
(`/items/search`, `/items/query`, `/items/list`, `/memories/*`, `/search`, colon-verbs).

**Demo approach:** prove memory through the **portal Memory view** plus **behavioural
cross-conversation recall** (ask a follow-up in a new conversation and show the persona
preference applied). Observed input-token growth — ~465 vs ~250 baseline — is good
supporting evidence that memory is being injected into the prompt.

---

## 11. Operational commands

```bash
# hosted agent logs — NOTE: `azd ai agent logs` does not exist
azd ai agent invoke <service> --no-prompt "..."   # creates a session
azd ai agent sessions list
azd ai agent monitor <service> --session-id <id>

# telemetry smoke check
az monitor app-insights query --app <appId> --analytics-query "dependencies | count"
```

Shell quirks worth knowing:

- `az rest` fails on APIM policy XML (`'charmap' codec can't encode '\ufeff'`) — use
  `az account get-access-token` + `Invoke-RestMethod` instead.
- `az ... --query "[?...]"` filters break in PowerShell — use `-o json | ConvertFrom-Json`.
- `az monitor app-insights component show` takes `--app`, not `-n`.
- `az vm run-command` output is capped at ~4096 chars — move large files as chunked base64.
- Transient `HTTP 500`s occur on the responses API at a low rate; `scripts/seed_rerun.py`
  retries 3× with backoff.

---

## 12. Seeding demo data

`scripts/seed_rerun.py` generates the full narrative: memory capture, 5 advisor prompts,
4 FNOL claims (each exercising toolbox + A2A), and 3 cross-conversation memory-recall
prompts. Latest run: **ok=12, fail=2** (the 2 failures are transient 500s on memory
preference capture; those personas were already captured in an earlier run).

Full transcript with prompts, outputs, timings and token counts:
[`demo-seed-transcript.md`](./demo-seed-transcript.md).

Run it, wait ~2 minutes, then screenshot the Application Map and the end-to-end
transaction view.
