"""Provision and seed the standalone public Foundry managed-Memory demo.

The target project must be public because managed Memory preview does not
support VNet-integrated Foundry projects.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from azure.identity import DefaultAzureCredential

PROJECT_ENDPOINT = os.environ.get(
    "FOUNDRY_PROJECT_ENDPOINT",
    "https://ai-aigw-chat-kj.services.ai.azure.com/api/projects/"
    "ai-aigw-chat-kj-project",
)
MEMORY_API_VERSION = "2025-11-15-preview"
AGENT_API_VERSION = "v1"
STORE_NAME = "underwriter-memory-demo-store"
USER_PRINCIPAL = os.environ.get(
    "MEMORY_DEMO_USER_PRINCIPAL",
    "joshikunal@joshikun.com",
)
USER_ID = os.environ.get(
    "MEMORY_DEMO_USER_ID",
    "b7dbc99c-2583-4c12-a839-e8447010dc79_48640a7a-0e09-4f2d-87c1-d483b3c9519d",
)
DEFINITION_PATH = (
    Path(__file__).resolve().parents[1]
    / "agents"
    / "prompt-agents"
    / "memory-preference-demo-agent.json"
)

credential = DefaultAzureCredential()


def request(method, path, body=None, *, memory_user=False, timeout=300):
    token = credential.get_token("https://ai.azure.com/.default").token
    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Foundry-Features": "MemoryStores=V1Preview",
    }
    if memory_user:
        headers["x-memory-user-id"] = USER_ID
    req = urllib.request.Request(
        PROJECT_ENDPOINT + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = response.read()
            return response.status, json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        details = exc.read().decode()
        raise RuntimeError(f"{method} {path} failed ({exc.code}): {details}") from exc


def ensure_store():
    try:
        _, store = request(
            "GET",
            f"/memory_stores/{STORE_NAME}?api-version={MEMORY_API_VERSION}",
        )
        return store
    except RuntimeError as exc:
        if "(404)" not in str(exc):
            raise

    _, store = request(
        "POST",
        f"/memory_stores?api-version={MEMORY_API_VERSION}",
        {
            "name": STORE_NAME,
            "description": (
                "User-scoped underwriting preferences for the public managed-Memory demo."
            ),
            "definition": {
                "kind": "default",
                "chat_model": "gpt-4.1-mini",
                "embedding_model": "text-embedding-3-small",
                "options": {
                    "chat_summary_enabled": True,
                    "user_profile_enabled": True,
                    "procedural_memory_enabled": True,
                    "default_ttl_seconds": 0,
                    "user_profile_details": (
                        "Underwriting output format, ordering, currency, and review "
                        "preferences. Exclude medical details, credentials, bank data, "
                        "protected-class attributes, and precise personal location."
                    ),
                },
            },
        },
    )
    return store


def deploy_agent():
    document = json.loads(DEFINITION_PATH.read_text(encoding="utf-8"))
    _, version = request(
        "POST",
        f"/agents/{document['name']}/versions?api-version={AGENT_API_VERSION}",
        {
            "description": document["description"],
            "definition": document["definition"],
        },
    )
    return document["name"], version["version"]


def new_conversation():
    _, conversation = request("POST", "/openai/v1/conversations", {})
    return conversation["id"]


def invoke(agent_name, conversation_id, text):
    _, response = request(
        "POST",
        "/openai/v1/responses",
        {
            "agent_reference": {
                "type": "agent_reference",
                "name": agent_name,
            },
            "conversation": conversation_id,
            "input": text,
        },
        memory_user=True,
        timeout=600,
    )
    return response


def output_text(response):
    return "\n".join(
        content.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text" and content.get("text")
    )


def seed_preferences(agent_name):
    prompts = [
        "Remember that I prefer underwriting summaries in no more than five concise bullets.",
        "Remember that I want loss ratio first and total insured value second.",
        "Remember that I use USD and require explicit human review for adverse recommendations.",
    ]
    conversation_id = new_conversation()
    for prompt in prompts:
        response = invoke(agent_name, conversation_id, prompt)
        commands = [
            item
            for item in response.get("output", [])
            if item.get("type") in {
                "memory_command_call",
                "memory_command_preview_call",
            }
        ]
        if not commands or any(item.get("status") != "completed" for item in commands):
            raise RuntimeError(
                "Memory command did not complete: "
                + json.dumps(response.get("output", []))
            )
        print(output_text(response))
        time.sleep(3)


def search_preferences():
    _, result = request(
        "POST",
        f"/memory_stores/{STORE_NAME}:search_memories"
        f"?api-version={MEMORY_API_VERSION}",
        {
            "scope": USER_ID,
            "user_principal": USER_PRINCIPAL,
            "items": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "What are my underwriting output preferences?",
                        }
                    ],
                }
            ],
            "options": {"max_memories": 10},
        },
    )
    return result


def main():
    store = ensure_store()
    agent_name, version = deploy_agent()
    seed_preferences(agent_name)
    memories = search_preferences()
    recall = invoke(
        agent_name,
        new_conversation(),
        "List my saved underwriting preferences. Do not add any new preferences.",
    )
    print(
        json.dumps(
            {
                "project_endpoint": PROJECT_ENDPOINT,
                "store": store["name"],
                "agent": agent_name,
                "version": version,
                "scope": USER_ID,
                "memory_count": len(memories.get("memories", [])),
                "memories": memories.get("memories", []),
                "cross_conversation_recall": output_text(recall),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
