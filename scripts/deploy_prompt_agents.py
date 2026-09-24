"""Deploy the two prompt-agent definitions from JSON files.

Run inside the jump host because the Foundry project is VNet isolated.
Each POST creates a new immutable version and @latest becomes active.
"""
import json
import os
import urllib.error
import urllib.request

from azure.identity import DefaultAzureCredential

ENDPOINT = (
    "https://aifoundrydemo3zbz.services.ai.azure.com/api/projects/insurance3zbz"
)
DEFINITIONS = os.environ.get("DEFINITIONS", r"C:\prompt-agents")


def post(name, definition):
    token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
    body = {
        "description": definition.get("description", ""),
        "definition": definition["definition"],
    }
    request = urllib.request.Request(
        f"{ENDPOINT}/agents/{name}/versions?api-version=v1",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Foundry-Features": "MemoryStores=V1Preview",
        },
    )
    try:
        return 200, json.loads(urllib.request.urlopen(request, timeout=180).read())
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:1200]


for filename in (
    "policy-coverage-advisor.json",
    "underwriting-risk-summarizer.json",
):
    path = os.path.join(DEFINITIONS, filename)
    document = json.load(open(path, encoding="utf-8"))
    code, result = post(document["name"], document)
    if code != 200:
        print(f"{document['name']}: FAILED {code} {result}")
    else:
        tools = [
            tool["type"]
            for tool in result.get("definition", {}).get("tools", [])
        ]
        print(
            f"{document['name']}: v{result['version']} active; "
            f"tools={','.join(tools)}"
        )
