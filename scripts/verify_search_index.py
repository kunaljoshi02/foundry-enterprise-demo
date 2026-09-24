import json, urllib.request, urllib.error
from azure.identity import DefaultAzureCredential

SEARCH="https://aifoundrydemo3zbzsearch.search.windows.net"
FOUNDRY="https://aifoundrydemo3zbz.services.ai.azure.com"
API="2024-07-01"; INDEX="contoso-policy-wordings"
cred=DefaultAzureCredential()

def _req(url,tok,body=None,method="GET"):
    data=json.dumps(body).encode() if body is not None else None
    r=urllib.request.Request(url,data=data,headers={"Authorization":"Bearer "+tok,"Content-Type":"application/json"},method=method)
    try:
        raw=urllib.request.urlopen(r,timeout=120).read(); return 200,(json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e: return e.code,e.read().decode()[:600]

def embed(t):
    tok=cred.get_token("https://ai.azure.com/.default").token
    c,r=_req(FOUNDRY+"/openai/deployments/text-embedding-3-small/embeddings?api-version=2024-02-01",tok,{"input":[t]},"POST")
    return r["data"][0]["embedding"]

tok=cred.get_token("https://search.azure.com/.default").token
c,r=_req(SEARCH+"/indexes/%s/docs/$count?api-version=%s"%(INDEX,API),tok)
print("count:",c,r)

for q in ["storm damaged my roof and a tree fell on the garage",
          "I was delivering food for an app when the crash happened",
          "customer slipped on a wet floor, no warning sign was put out",
          "washing machine leaked, do you pay to find the leak"]:
    v=embed(q)
    body={"search":q,"top":3,"select":"id,product,section_ref,clause_type,title",
          "queryType":"semantic","semanticConfiguration":"sem-cfg",
          "vectorQueries":[{"kind":"vector","vector":v,"fields":"content_vector","k":10}]}
    c,r=_req(SEARCH+"/indexes/%s/docs/search?api-version=%s"%(INDEX,API),tok,body,"POST")
    print("\nQ:",q,"->",c)
    if c==200:
        for d in r["value"]:
            print("   %-10s %-6s %-10s %s"%(d["product"],d["section_ref"],d["clause_type"],d["title"]))
    else: print("  ",r)
