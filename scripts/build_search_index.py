"""Create the contoso-policy-wordings AI Search index and ingest the corpus.

Run from the jump host - the search service is reachable only inside the VNet.
Idempotent: recreates the index definition and re-uploads all documents.
"""
import json
import os
import urllib.error
import urllib.request

from azure.identity import DefaultAzureCredential

SEARCH = "https://aifoundrydemo3zbzsearch.search.windows.net"
FOUNDRY = "https://aifoundrydemo3zbz.services.ai.azure.com"
API = "2024-07-01"
INDEX = "contoso-policy-wordings"
EMBED_MODEL = "text-embedding-3-small"
DIMS = 1536
CORPUS = r"C:\policy-wordings.json"

cred = DefaultAzureCredential()


def _req(url, token, body=None, method="GET"):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method=method,
    )
    try:
        raw = urllib.request.urlopen(r, timeout=300).read()
        return 200, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:900]


def search_call(path, body=None, method="GET"):
    tok = cred.get_token("https://search.azure.com/.default").token
    return _req(SEARCH + path, tok, body, method)


def embed(texts):
    """Embed via the Foundry account's own deployment."""
    tok = cred.get_token("https://ai.azure.com/.default").token
    url = "%s/openai/deployments/%s/embeddings?api-version=2024-02-01" % (FOUNDRY, EMBED_MODEL)
    code, res = _req(url, tok, {"input": texts}, "POST")
    if code != 200:
        raise RuntimeError("embed failed %s %s" % (code, res))
    return [d["embedding"] for d in res["data"]]


INDEX_DEF = {
    "name": INDEX,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
        {"name": "product", "type": "Edm.String", "filterable": True, "facetable": True, "searchable": True},
        {"name": "policy_form", "type": "Edm.String", "filterable": True, "facetable": True, "searchable": True},
        {"name": "section_ref", "type": "Edm.String", "filterable": True, "searchable": True},
        {"name": "clause_type", "type": "Edm.String", "filterable": True, "facetable": True, "searchable": True},
        {"name": "title", "type": "Edm.String", "searchable": True},
        {"name": "content", "type": "Edm.String", "searchable": True},
        {
            "name": "content_vector",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "retrievable": False,
            "dimensions": DIMS,
            "vectorSearchProfile": "vp",
        },
    ],
    "vectorSearch": {
        "algorithms": [{"name": "hnsw-cfg", "kind": "hnsw"}],
        "profiles": [{"name": "vp", "algorithm": "hnsw-cfg"}],
    },
    "semantic": {
        "configurations": [
            {
                "name": "sem-cfg",
                "prioritizedFields": {
                    "titleField": {"fieldName": "title"},
                    "prioritizedContentFields": [{"fieldName": "content"}],
                    "prioritizedKeywordsFields": [
                        {"fieldName": "clause_type"},
                        {"fieldName": "policy_form"},
                    ],
                },
            }
        ]
    },
}


def main():
    docs = json.load(open(CORPUS, encoding="utf-8"))
    print("corpus documents:", len(docs))

    code, res = search_call("/indexes/%s?api-version=%s" % (INDEX, API), method="DELETE")
    print("delete existing index ->", code)

    code, res = search_call("/indexes?api-version=%s" % API, INDEX_DEF, "POST")
    if code != 200:
        print("CREATE INDEX FAILED", code, res)
        return
    print("index created:", INDEX)

    # embed in batches so a single oversized request cannot fail the whole run
    batch = 16
    vectors = []
    for i in range(0, len(docs), batch):
        chunk = docs[i : i + batch]
        texts = ["%s. %s" % (d["title"], d["content"]) for d in chunk]
        vectors.extend(embed(texts))
        print("embedded", len(vectors), "/", len(docs))

    payload = []
    for d, v in zip(docs, vectors):
        rec = dict(d)
        rec["@search.action"] = "mergeOrUpload"
        rec["content_vector"] = v
        payload.append(rec)

    for i in range(0, len(payload), 20):
        code, res = search_call(
            "/indexes/%s/docs/index?api-version=%s" % (INDEX, API),
            {"value": payload[i : i + 20]},
            "POST",
        )
        if code != 200:
            print("UPLOAD FAILED", code, res)
            return
        print("uploaded batch", i // 20 + 1)

    code, res = search_call("/indexes/%s/docs/$count?api-version=%s" % (INDEX, API))
    print("indexed document count ->", code, res)


if __name__ == "__main__":
    main()
