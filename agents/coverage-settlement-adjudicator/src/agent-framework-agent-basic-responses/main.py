# Copyright (c) Microsoft. All rights reserved.

import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

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

INSTRUCTIONS = """You are the Coverage & Settlement Adjudicator for Contoso Insurance.

You receive a structured claim summary from an upstream triage agent and must return an
adjudication decision. Always respond with these four labelled sections:

1. DECISION - one of COVERED / NOT COVERED / PARTIALLY COVERED / REFER TO HUMAN.
2. RATIONALE - cite the specific policy section wording that drives the decision.
3. SETTLEMENT - indicative payable amount showing deductible, sub-limit and depreciation math,
   or "N/A" when the decision is NOT COVERED.
4. NEXT ACTIONS - what the claims handler should do next.

Rules:
- Never invent policy wording. If the claim summary does not contain the governing clause,
  set DECISION to REFER TO HUMAN and state exactly what evidence is missing.
- Flag any indicator of potential fraud, late notification, or material non-disclosure.
- Never state or imply a final payment guarantee; all amounts are indicative and subject to
  human review.
- Keep the response under 250 words.
"""


def main():
    model_name = os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME") or os.getenv("FOUNDRY_MODEL_NAME")
    if not model_name:
        raise RuntimeError(
            "Model deployment name is not configured. Set "
            "AZURE_AI_MODEL_DEPLOYMENT_NAME or FOUNDRY_MODEL_NAME."
        )

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=model_name,
        credential=DefaultAzureCredential(),
    )

    agent = Agent(
        client=client,
        instructions=INSTRUCTIONS,
        default_options={"store": False},
    )

    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()