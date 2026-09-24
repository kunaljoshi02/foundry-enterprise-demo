"""Run representative live checks against all four demo agents.

Run this from the VNet jump host because the Foundry project is private.
"""

import json
import sys
import time

import requests
from azure.identity import DefaultAzureCredential

ACCOUNT = "https://aifoundrydemo3zbz.services.ai.azure.com"
PROJECT = ACCOUNT + "/api/projects/insurance3zbz"
HEADERS = {"Foundry-Features": "MemoryStores=V1Preview"}
_credential = DefaultAzureCredential()


def post(url, body, timeout=900):
    headers = {
        **HEADERS,
        "Authorization": "Bearer "
        + _credential.get_token("https://ai.azure.com/.default").token,
        "Content-Type": "application/json",
    }
    return requests.post(url, headers=headers, json=body, timeout=timeout)


def output_text(payload):
    return "".join(
        item.get("text", "")
        for output in payload.get("output", [])
        for item in output.get("content", [])
        if item.get("type") == "output_text"
    )


def report(label, response, started):
    print(f"\n=== {label} ({time.time() - started:.1f}s) ===")
    print("HTTP", response.status_code)
    if response.status_code >= 300:
        print(response.text[:4000])
        return
    payload = response.json()
    print("output_types:", [item.get("type") for item in payload.get("output", [])])
    for item in payload.get("output", []):
        if item.get("type") != "message":
            print("tool_event:", json.dumps(item, ensure_ascii=False)[:3000])
    print("usage:", json.dumps(payload.get("usage", {})))
    print(output_text(payload)[:6000])


def prompt_agent(name, prompt, conversation=None):
    body = {
        "agent_reference": {"type": "agent_reference", "name": name},
        "input": prompt,
    }
    if conversation:
        body["conversation"] = conversation
    started = time.time()
    report(name, post(PROJECT + "/openai/v1/responses", body), started)


def hosted_agent(name, prompt):
    url = (
        f"{PROJECT}/agents/{name}/endpoint/protocols/openai/responses"
        "?api-version=v1"
    )
    started = time.time()
    report(name, post(url, {"input": prompt}), started)


targets = set(sys.argv[1:] or ("prompt", "hosted"))

if "prompt" in targets:
    prompt_agent(
        "policy-coverage-advisor",
        (
            "Policy P-7781 is a Contoso Home policy. A washing-machine hose failed "
            "suddenly, damaging the kitchen. Repairs are GBP 8,200 and locating the "
            "leak cost GBP 1,400. Explain coverage, exclusions, excess, trace-and-access "
            "limit, and cite the exact retrieved policy clauses."
        ),
    )

    conversation_response = post(
        PROJECT + "/openai/v1/conversations",
        {"metadata": {"userId": "uw-demo-verification"}},
    )
    conversation_response.raise_for_status()
    prompt_agent(
        "underwriting-risk-summarizer",
        (
            "For the signed-in user, summarize this property submission and verify my "
            "profile before making an authority-sensitive recommendation. TIV GBP "
            "4,000,000; annual premium GBP 80,000; incurred losses over 3 years GBP "
            "144,000. Use Code Interpreter to calculate the three-year loss ratio and "
            "Web Search for one current UK flood-risk source. Apply Memory preferences "
            "if present, identify the OBO identity/role result, and require human approval."
        ),
        conversation_response.json()["id"],
    )

if "hosted" in targets or "adjudicator" in targets:
    hosted_agent(
        "coverage-settlement-adjudicator",
        (
            "Contoso Home policy P-7781. Sudden washing-machine hose escape of water. "
            "Building damage GBP 8,200; trace-and-access GBP 1,400. No gradual leakage. "
            "Retrieve the governing clauses, load the required skills, calculate the "
            "indicative settlement, and state that human review is required."
        ),
    )

if "hosted" in targets or "triage" in targets:
    hosted_agent(
        "claims-intake-triage-agent",
        (
            "FNOL for policy L-2044. Customer slipped on a wet supermarket floor today. "
            "No warning sign was displayed. Estimated injury reserve GBP 18,000, reported "
            "the same day. Load the required communication skills, retrieve relevant "
            "clauses, and delegate every coverage decision to the adjudicator."
        ),
    )
