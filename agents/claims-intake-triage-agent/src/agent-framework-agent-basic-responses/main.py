# Claims Intake & Triage Orchestrator - Foundry hosted agent (multi-agent via A2A)
import asyncio
import os
import uuid
from typing import Annotated

import httpx
from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import FoundryToolbox, ResponsesHostServer
from azure.identity import DefaultAzureCredential
from pydantic import Field

ADJUDICATOR_A2A_URL = os.environ["ADJUDICATOR_A2A_URL"]
_credential = DefaultAzureCredential()


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
        return "Adjudicator returned an error: " + str(data["error"])
    texts = []
    for artifact in data.get("result", {}).get("artifacts", []):
        for part in artifact.get("parts", []):
            if part.get("kind") == "text":
                texts.append(part.get("text", ""))
    return "\n".join(texts) if texts else "Adjudicator returned no content."


INSTRUCTIONS = """You are the Claims Intake & Triage Orchestrator for a commercial and personal lines insurer.

For every incoming claim notification (FNOL):
1. CLASSIFY: line of business (auto, property, liability, specialty), peril, and urgency (P1 emergency / P2 standard / P3 low).
2. EXTRACT entities: policy number, claimant, date of loss, date reported, location, estimated loss, injuries, third parties.
3. DETECT red flags: late reporting, prior similar claims, inconsistent narrative, coverage lapse indicators.
4. ROUTE: fast-track (simple, low value, clear coverage) vs complex (injury, liability dispute, large loss, suspected fraud).
5. DELEGATE: you MUST call the adjudicate_claim tool for every claim, passing all extracted facts. Report its decision verbatim in your Adjudicator Findings section.
6. Use the code interpreter tool for reserve, depreciation or deductible arithmetic when useful.

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
        tools=[toolbox, adjudicate_claim],
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())