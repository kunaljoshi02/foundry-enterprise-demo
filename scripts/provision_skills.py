"""Provision versioned Foundry skills from repo/skills using the preview REST API.

Run from the VNet jump host because the Foundry project has public access disabled.
"""
import json
import os
import sys
import uuid
import urllib.error
import urllib.request

from azure.identity import DefaultAzureCredential

PROJECT_ENDPOINT = (
    "https://aifoundrydemo3zbz.services.ai.azure.com/api/projects/insurance3zbz"
)
FEATURES = "Skills=V1Preview"
SKILLS_ROOT = os.environ.get("SKILLS_ROOT", r"C:\skills")


def multipart_file(path):
    boundary = "----foundry" + uuid.uuid4().hex
    content = open(path, "rb").read()
    name = os.path.basename(path)
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"; filename="{name}"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def request(path, body=None, content_type="application/json", method="GET"):
    token = DefaultAzureCredential().get_token("https://ai.azure.com/.default").token
    req = urllib.request.Request(
        PROJECT_ENDPOINT + path,
        data=body,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": content_type,
            "Foundry-Features": FEATURES,
        },
    )
    try:
        raw = urllib.request.urlopen(req, timeout=180).read()
        return 200, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()[:1000]


def main():
    names = sorted(
        name
        for name in os.listdir(SKILLS_ROOT)
        if os.path.isfile(os.path.join(SKILLS_ROOT, name, "SKILL.md"))
    )
    if not names:
        raise SystemExit("No skills found under " + SKILLS_ROOT)

    for name in names:
        body, content_type = multipart_file(
            os.path.join(SKILLS_ROOT, name, "SKILL.md")
        )
        code, result = request(
            f"/skills/{name}/versions?api-version=v1",
            body,
            content_type,
            "POST",
        )
        if code != 200:
            print(f"{name}: FAILED {code} {result}")
            continue

        version = result["version"]
        update = json.dumps({"default_version": version}).encode()
        update_code, update_result = request(
            f"/skills/{name}?api-version=v1", update, method="POST"
        )
        if update_code != 200:
            print(
                f"{name}: uploaded v{version}, failed to set default "
                f"{update_code} {update_result}"
            )
            continue
        print(f"{name}: v{version} created and set as default")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
