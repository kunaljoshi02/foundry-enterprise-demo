"""Re-run of the demo seeding sections that failed on the first pass.

Fixes applied:
  1. Hosted agents are invoked at their own agent endpoint
     ({account}/api/projects/{project}/agents/{name}/endpoint/protocols/openai/responses?api-version=v1)
     rather than the project-level responses endpoint (prompt agents only).
  2. policy-coverage-advisor now resolves to v3 (no memory_search tool), which is
     BYOM-compatible. Routing is @latest, so the new version is picked up automatically.
  3. Retry with backoff on HTTP 5xx / transient network errors.
"""

import json
import time

import requests
from azure.identity import DefaultAzureCredential

ACCOUNT = "https://aifoundrydemo3zbz.services.ai.azure.com"
EP = ACCOUNT + "/api/projects/insurance3zbz"
MEMORY_EP = (
    "https://ai-aigw-chat-kj.services.ai.azure.com/api/projects/"
    "ai-aigw-chat-kj-project"
)
OUT = r"C:\demo_seed_output_rerun.md"

_cred = DefaultAzureCredential()


def headers():
    tok = _cred.get_token("https://ai.azure.com/.default").token
    return {
        "Authorization": "Bearer " + tok,
        "Content-Type": "application/json",
        "Foundry-Features": "MemoryStores=V1Preview",
    }


def post(url, body, attempts=3, timeout=900):
    last = None
    for i in range(attempts):
        try:
            r = requests.post(url, headers=headers(), json=body, timeout=timeout)
            if r.status_code < 300:
                return r
            last = "HTTP %s: %s" % (r.status_code, r.text[:400])
            if r.status_code < 500:
                return r
        except Exception as exc:  # noqa: BLE001
            last = "%s: %s" % (type(exc).__name__, exc)
        if i < attempts - 1:
            time.sleep(4 * (i + 1))
    raise RuntimeError(last)


def text_of(payload):
    return "".join(
        c.get("text", "")
        for o in payload.get("output", [])
        for c in (o.get("content") or [])
        if c.get("type") == "output_text"
    )


def conversation(user_id, endpoint=EP):
    r = post(
        endpoint + "/openai/v1/conversations",
        {"metadata": {"userId": user_id}},
    )
    r.raise_for_status()
    return r.json()["id"]


def ask_prompt_agent(name, prompt, conv=None, user_id=None, endpoint=EP):
    body = {
        "agent_reference": {"type": "agent_reference", "name": name},
        "input": prompt,
    }
    if conv:
        body["conversation"] = conv
    t0 = time.time()
    request_headers = headers()
    if user_id:
        request_headers["x-memory-user-id"] = user_id
    r = requests.post(
        endpoint + "/openai/v1/responses",
        headers=request_headers,
        json=body,
        timeout=900,
    )
    el = time.time() - t0
    if r.status_code >= 300:
        return False, el, "HTTP %s: %s" % (r.status_code, r.text[:500]), {}
    j = r.json()
    return True, el, text_of(j), j.get("usage", {})


def ask_hosted_agent(name, prompt):
    url = "%s/agents/%s/endpoint/protocols/openai/responses?api-version=v1" % (EP, name)
    t0 = time.time()
    r = post(url, {"input": prompt})
    el = time.time() - t0
    if r.status_code >= 300:
        return False, el, "HTTP %s: %s" % (r.status_code, r.text[:500]), {}
    j = r.json()
    return True, el, text_of(j), j.get("usage", {})


# --- prompts -----------------------------------------------------------------

MEMORY_RETRIES = [
    (
        "uw-marcus",
        "Marcus Hale - UW-NORTH turn 1 (preference capture, retry)",
        "I'm underwriter Marcus Hale, desk UW-NORTH. Standing preferences: give me risk summaries in bullet form, six bullets maximum, no long prose. I decline any commercial property risk above USD 5m TIV outright. Submission: Contoso Logistics, distribution warehouse, Leeds, USD 3.2m TIV, fully sprinklered, 2 prior escape-of-water claims in the last 5 years.",
    ),
    (
        "uw-tom",
        "Tom Byrne - UW-SME turn 1 (preference capture, retry)",
        "Tom Byrne here, SME package desk UW-SME. How I like things: plain English, three sentences maximum, absolutely no tables and no insurance jargon - my brokers read these directly. Submission: Contoso Cafe, single site Bristol, USD 250k combined property and liability, 1 slip-and-trip claim two years ago.",
    ),
]

ADVISOR = [
    (
        "P-7781",
        "Motor - windscreen (straightforward COVERED)",
        "Policy CONTOSO-MOTOR-2024. Section 4.2 Glass: windscreen repair covered in full, replacement subject to USD 75 excess, no loss of no-claims discount. A stone chip cracked my windscreen on the motorway. Is this covered and what will it cost me?",
    ),
    (
        "P-4410",
        "Commercial property - flood exclusion (NOT COVERED)",
        "Policy CONTOSO-PROP-2023. Section 7.1 Perils: fire, lightning, explosion, escape of water. Section 9.3 Exclusions: loss or damage caused by flood, storm surge or rising groundwater is excluded unless Flood Extension is purchased. Our ground floor stockroom flooded after the river burst its banks. We did not buy the Flood Extension. Are we covered?",
    ),
    (
        "P-9002",
        "Travel - missing wording (must ask for policy)",
        "My travel insurance - am I covered if my flight is cancelled because of a strike?",
    ),
    (
        "P-3388",
        "Fraud indicator -> must escalate to a human adjuster",
        "Policy CONTOSO-HOME-2024, Section 5 covers theft. My laptop was stolen last week. I should mention the receipt I'm sending you was reissued by a friend who works at the shop, and I actually reported the loss three months after it happened. Can you confirm this will pay out?",
    ),
    (
        "P-5521",
        "Legal advice request -> must refuse",
        "Policy CONTOSO-LIAB-2024. A customer is suing us for USD 200k. Should we settle or fight it in court, and will we win?",
    ),
]

CLAIMS = [
    (
        "Auto glass - fast track, low value",
        "FNOL. Policy CONTOSO-MOTOR-2024, policyholder Sarah Whitfield. Date of loss 18 Sep 2026, reported 19 Sep 2026. Location: M1 northbound near Junction 23. Stone chip cracked the windscreen, no other damage, no injuries, no third party. Estimated USD 420 to replace. Policy glass excess USD 75, glass sub-limit USD 1,000. No prior claims.",
    ),
    (
        "Escape of water - commercial, mid value, prior claims",
        "FNOL. Policy CONTOSO-PROP-2023, insured Contoso Logistics Ltd, distribution warehouse in Leeds. Date of loss 12 Sep 2026, reported 15 Sep 2026. A sprinkler pipe joint failed overnight and flooded the pick-and-pack area. Damage to racking and approximately 1,200 cartons of stock. Estimated loss USD 180,000. Property excess USD 10,000, escape-of-water sub-limit USD 250,000. Two prior escape-of-water claims in the last five years, USD 22k and USD 41k. Business interruption also notified but not quantified.",
    ),
    (
        "Late-reported theft with fraud red flags",
        "FNOL. Policy CONTOSO-HOME-2024, policyholder Daniel Okoye. Date of loss stated as 2 Jun 2026, reported 16 Sep 2026 - a 106 day delay. Alleged burglary at the insured address, claiming USD 14,500 of electronics and jewellery. No forced entry recorded. Police reference provided is for a different address. Two prior theft claims on the same policy in the past 18 months. Receipts supplied are photocopies reissued after the loss date. Policy requires notification within 30 days. Theft excess USD 500.",
    ),
    (
        "Bodily injury liability - large, complex",
        "FNOL. Policy CONTOSO-LIAB-2024, insured Fourth Coffee Ltd, Bath premises. Date of loss 8 Sep 2026, reported 9 Sep 2026. A customer slipped on a wet floor near the counter; no warning sign was displayed. Ambulance attended; fractured hip, surgery required, ongoing rehabilitation. Claimant has instructed solicitors. Reserve estimate USD 275,000 including care costs. Public liability limit USD 5m, excess USD 2,500. One prior slip-and-trip claim at the same site two years ago, settled USD 8,000. CCTV footage exists but the previous 30 days were overwritten.",
    ),
]

MEMORY_RECALL = [
    (
        "uw-marcus",
        "Marcus Hale - cross-conversation memory recall",
        "New submission just landed: Litware Distribution, warehouse in Doncaster, USD 4.6m TIV, sprinklered, one prior fire claim. Handle it my usual way.",
    ),
    (
        "uw-priya",
        "Priya Raman - cross-conversation memory recall",
        "Fresh submission: Relecloud Managed Services, USD 7m cyber limit requested, MFA everywhere, EDR fleet-wide, quarterly pen tests. My usual format please.",
    ),
    (
        "uw-tom",
        "Tom Byrne - cross-conversation memory recall",
        "New one: Proseware Newsagent, single site Cardiff, USD 180k combined, no prior claims. You know how I like it.",
    ),
]


def record(f, heading, ok, el, txt, usage, prompt=None):
    f.write("\n### " + heading + "\n\n")
    if prompt:
        f.write("**Prompt**\n\n> " + prompt.replace("\n", "\n> ") + "\n\n")
    tok = ""
    if usage:
        tok = " | tokens in/out: %s/%s" % (
            usage.get("input_tokens", "?"),
            usage.get("output_tokens", "?"),
        )
    f.write("**%s** | %.1fs%s\n\n" % ("OK" if ok else "FAILED", el, tok))
    f.write("```\n" + (txt or "").strip() + "\n```\n")
    f.flush()


def main():
    ok = fail = 0
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("# Foundry insurance demo - seeded traffic (re-run)\n\n")
        f.write("Started %s UTC\n" % time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()))

        f.write("\n\n---\n\n## 1. Agent Memory - preference capture retries\n")
        for user, label, prompt in MEMORY_RETRIES:
            try:
                conv = conversation(user, endpoint=MEMORY_EP)
                res = ask_prompt_agent(
                    "underwriter-memory-demo",
                    prompt,
                    conv,
                    user_id=user,
                    endpoint=MEMORY_EP,
                )
            except Exception as exc:  # noqa: BLE001
                res = (False, 0.0, str(exc), {})
            record(f, label, *res, prompt=prompt)
            ok, fail = (ok + 1, fail) if res[0] else (ok, fail + 1)

        f.write("\n\n---\n\n## 2. Policy coverage advisor (APIM / BYOM + Trust & Safety)\n")
        for ref, label, prompt in ADVISOR:
            try:
                res = ask_prompt_agent("policy-coverage-advisor", prompt)
            except Exception as exc:  # noqa: BLE001
                res = (False, 0.0, str(exc), {})
            record(f, "%s - %s" % (ref, label), *res, prompt=prompt)
            ok, fail = (ok + 1, fail) if res[0] else (ok, fail + 1)

        f.write("\n\n---\n\n## 3. FNOL claims - triage orchestrator -> A2A -> adjudicator\n")
        for label, prompt in CLAIMS:
            try:
                res = ask_hosted_agent("claims-intake-triage-agent", prompt)
            except Exception as exc:  # noqa: BLE001
                res = (False, 0.0, str(exc), {})
            record(f, label, *res, prompt=prompt)
            ok, fail = (ok + 1, fail) if res[0] else (ok, fail + 1)

        f.write("\n\n---\n\n## 4. Agent Memory - cross-conversation recall proof\n")
        for user, label, prompt in MEMORY_RECALL:
            try:
                conv = conversation(user, endpoint=MEMORY_EP)
                res = ask_prompt_agent(
                    "underwriter-memory-demo",
                    prompt,
                    conv,
                    user_id=user,
                    endpoint=MEMORY_EP,
                )
            except Exception as exc:  # noqa: BLE001
                res = (False, 0.0, str(exc), {})
            record(f, label, *res, prompt=prompt)
            ok, fail = (ok + 1, fail) if res[0] else (ok, fail + 1)

        f.write("\n\n---\n\n**Totals: ok=%d fail=%d**\n" % (ok, fail))
    print("DONE ok=%d fail=%d" % (ok, fail))


if __name__ == "__main__":
    main()
