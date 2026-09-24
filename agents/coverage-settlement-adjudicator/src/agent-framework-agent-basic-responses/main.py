# Copyright (c) Microsoft. All rights reserved.

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
from dotenv import load_dotenv
from pydantic import Field

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


load_dotenv()
_credential = DefaultAzureCredential()
TOOLBOX_ENDPOINT = os.environ["TOOLBOX_ENDPOINT"]
_SKILLS = {
    "adjudication-rationale",
    "regulatory-disclosure",
    "customer-comms-tone",
}


async def load_insurance_skill(
    skill_name: Annotated[
        str,
        Field(
            description=(
                "Adjudication skill to load. Allowed values: "
                "adjudication-rationale, regulatory-disclosure, "
                "customer-comms-tone."
            )
        ),
    ],
) -> str:
    """Load the current version of an adjudication skill from the toolbox."""
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

INSTRUCTIONS = """You are the Coverage & Settlement Adjudicator for Contoso Insurance.

You receive a structured claim summary from an upstream triage agent and must return an
adjudication decision. Always respond with these four labelled sections:

1. DECISION - one of COVERED / NOT COVERED / PARTIALLY COVERED / REFER TO HUMAN.
2. RATIONALE - cite the specific policy section wording that drives the decision.
3. SETTLEMENT - indicative payable amount showing deductible, sub-limit and depreciation math,
   or "N/A" when the decision is NOT COVERED.
4. NEXT ACTIONS - what the claims handler should do next.

Rules:
- Call load_insurance_skill("adjudication-rationale") before every decision and
  load_insurance_skill("regulatory-disclosure") before returning an adverse or
  conditional recommendation.
- Use the policy search tool before making a coverage decision. Cite only clauses
  returned by the tool. If the first result set lacks the governing insuring clause,
  run a second targeted search using the line of business, peril, premises duty,
  and relevant policy condition before referring to a human.
- Use the code interpreter for excess, sub-limit, depreciation, or net-settlement math.
- Never invent policy wording. If the claim summary does not contain the governing clause,
  set DECISION to REFER TO HUMAN and state exactly what evidence is missing.
- Flag any indicator of potential fraud, late notification, or material non-disclosure.
- Never state or imply a final payment guarantee; all amounts are indicative and subject to
  human review.
- Keep the response under 250 words.
"""


async def main():
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
    if not model_name:
        raise RuntimeError(
            "Model deployment name is not configured. Set "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME."
        )

    toolbox = FoundryToolbox(_credential)
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model_name,
        credential=_credential,
    )

    agent = Agent(
        client=client,
        instructions=INSTRUCTIONS,
        tools=[toolbox, load_insurance_skill],
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())