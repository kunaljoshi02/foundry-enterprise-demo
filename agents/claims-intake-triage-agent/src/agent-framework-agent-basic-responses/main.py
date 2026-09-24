# Claims Intake & Triage Orchestrator - Foundry hosted agent (multi-agent via A2A)
import asyncio
import json
import os
import uuid
from typing import Annotated

import httpx
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential
from pydantic import Field

from agent_protocols import (
    extract_a2a_text,
    extract_responses_text,
    is_hosted_agent_a2a_unsupported,
    responses_url_from_a2a_url,
)

# --- Observability: export OpenTelemetry traces/metrics to Application Insights ---
_APPINSIGHTS_CS = os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING")
if _APPINSIGHTS_CS:
    os.environ.setdefault("ENABLE_OTEL", "true")
    os.environ.setdefault("ENABLE_SENSITIVE_DATA", "true")
    _obs_ready = False
    try:
        from agent_framework.observability import setup_observability

        try:
            setup_observability(applicationinsights_connection_string=_APPINSIGHTS_CS)
        except TypeError:
            setup_observability()
        _obs_ready = True
    except Exception as _obs_exc:  # noqa: BLE001
        print("setup_observability unavailable: %s" % _obs_exc, flush=True)
    if not _obs_ready:
        try:
            from azure.monitor.opentelemetry import configure_azure_monitor

            configure_azure_monitor(connection_string=_APPINSIGHTS_CS)
            _obs_ready = True
        except Exception as _mon_exc:  # noqa: BLE001
            print("configure_azure_monitor failed: %s" % _mon_exc, flush=True)
    if _obs_ready:
        try:
            from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

            HTTPXClientInstrumentor().instrument()
        except Exception as _httpx_exc:  # noqa: BLE001
            print("httpx instrumentation failed: %s" % _httpx_exc, flush=True)
        print("Application Insights telemetry enabled.", flush=True)


ADJUDICATOR_A2A_URL = os.environ["ADJUDICATOR_A2A_URL"]
_credential = DefaultAzureCredential()
TOOLBOX_ENDPOINT = os.environ["TOOLBOX_ENDPOINT"]
_SKILLS = {
    "claims-tone",
    "regulatory-disclosure",
    "adjudication-rationale",
    "underwriting-appetite",
    "customer-comms-tone",
}


async def load_insurance_skill(
    skill_name: Annotated[
        str,
        Field(
            description=(
                "Insurance behavioral skill to load. Allowed values: claims-tone, "
                "regulatory-disclosure, adjudication-rationale, "
                "underwriting-appetite, customer-comms-tone."
            )
        ),
    ],
) -> str:
    """Load the current version of an insurance skill from the Foundry toolbox."""
    if skill_name not in _SKILLS:
        return "Unknown skill. Allowed values: " + ", ".join(sorted(_SKILLS))
    token = _credential.get_token("https://ai.azure.com/.default").token
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "resources/read",
        "params": {"uri": f"skill://{skill_name}/SKILL.md"},
    }
    async with httpx.AsyncClient(timeout=60.0) as http:
        response = await http.post(
            TOOLBOX_ENDPOINT,
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
            json=payload,
        )
    response.raise_for_status()
    result = response.json()
    if "error" in result:
        return "Skill load failed: " + json.dumps(result["error"])
    content = result.get("result", {}).get("contents", [])
    return "\n".join(item.get("text", "") for item in content if item.get("text"))


async def adjudicate_claim(
    claim_summary: Annotated[
        str,
        Field(description="Full claim facts: policy number, peril, loss description, estimated amount, deductible, sub-limits, prior claims, notification dates."),
    ],
) -> str:
    """Send a claim to the coverage-settlement-adjudicator specialist agent over A2A and return its coverage decision, rationale and indicative settlement."""
    token = _credential.get_token("https://ai.azure.com/.default").token
    payload = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": claim_summary}],
                "messageId": str(uuid.uuid4()),
                "kind": "message",
            },
            "configuration": {"blocking": True},
        },
    }
    async with httpx.AsyncClient(timeout=180.0) as http:
        resp = await http.post(
            ADJUDICATOR_A2A_URL,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            json=payload,
        )
    if resp.status_code >= 400:
        return "Adjudicator call failed with HTTP " + str(resp.status_code) + ": " + resp.text[:500]
    data = resp.json()
    if "error" in data:
        if not is_hosted_agent_a2a_unsupported(data["error"]):
            return "Adjudicator returned an A2A error: " + json.dumps(data["error"])

        responses_url = responses_url_from_a2a_url(ADJUDICATOR_A2A_URL)
        print(
            "A2A target rejected by Foundry; retrying hosted adjudicator over "
            "the Responses protocol.",
            flush=True,
        )
        async with httpx.AsyncClient(timeout=180.0) as http:
            fallback = await http.post(
                responses_url,
                headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                },
                json={"input": claim_summary},
            )
        if fallback.status_code >= 400:
            return (
                "Adjudicator Responses fallback failed with HTTP "
                + str(fallback.status_code)
                + ": "
                + fallback.text[:500]
            )
        fallback_data = fallback.json()
        text = extract_responses_text(fallback_data)
        if text:
            print(
                "Adjudicator Responses fallback completed: response_id="
                + str(fallback_data.get("id", "unknown"))
                + ", status="
                + str(fallback_data.get("status", "unknown")),
                flush=True,
            )
            return text
        return (
            "Adjudicator Responses fallback returned no assistant text: status="
            + str(fallback_data.get("status", "unknown"))
        )

    result = data.get("result")
    text = extract_a2a_text(result)
    if text:
        return text

    state = result.get("status", {}).get("state") if isinstance(result, dict) else None
    return "Adjudicator A2A response contained no text: state=" + str(state or "unknown")


INSTRUCTIONS = """You are the Claims Intake & Triage Orchestrator for a commercial and personal lines insurer.

For every incoming claim notification (FNOL):
1. CLASSIFY: line of business (auto, property, liability, specialty), peril, and urgency (P1 emergency / P2 standard / P3 low).
2. EXTRACT entities: policy number, claimant, date of loss, date reported, location, estimated loss, injuries, third parties.
3. DETECT red flags: late reporting, prior similar claims, inconsistent narrative, coverage lapse indicators.
4. ROUTE: fast-track (simple, low value, clear coverage) vs complex (injury, liability dispute, large loss, suspected fraud).
5. GROUND: use the policy search tool before delegation. Select the insuring clause,
   relevant definitions, exclusions, conditions, excesses, and limits.
6. DELEGATE: you MUST call adjudicate_claim for every claim, passing all extracted
   facts plus the verbatim clauses returned by policy search. Report its decision
   verbatim in your Adjudicator Findings section.
7. Use the code interpreter tool for reserve, depreciation or deductible arithmetic when useful.
8. Call load_insurance_skill("claims-tone") before drafting claimant-facing text and
   load_insurance_skill("regulatory-disclosure") before presenting a recommendation.

Always answer with these sections:
- Triage Summary
- Extracted Entities
- Red Flags
- Routing Decision
- Adjudicator Findings (from the specialist agent)
- Recommended Next Actions

Be concise and factual. Never invent policy wording. List missing facts under Recommended Next Actions.
"""


async def main():
    toolbox = FoundryToolbox(_credential)

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=_credential,
    )

    agent = Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=[toolbox, adjudicate_claim, load_insurance_skill],
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())