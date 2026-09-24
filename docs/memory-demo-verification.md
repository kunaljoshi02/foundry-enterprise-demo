# Managed Memory Demo Verification

Verified on 2026-09-24 against the existing public Foundry project:

| Asset | Value |
| --- | --- |
| Foundry account | `ai-aigw-chat-kj` |
| Project | `ai-aigw-chat-kj-project` |
| Project endpoint | `https://ai-aigw-chat-kj.services.ai.azure.com/api/projects/ai-aigw-chat-kj-project` |
| Agent | `underwriter-memory-demo` v1 |
| Memory store | `underwriter-memory-demo-store` |
| Chat model | `gpt-4.1-mini` |
| Embedding model | `text-embedding-3-small` |
| User principal | `joshikunal@joshikun.com` |
| Entra user object ID scope | `b7dbc99c-2583-4c12-a839-e8447010dc79` |

The scope is the tenant user's Entra object ID. Requests that use
`x-memory-user-id` must pass this exact value to store and retrieve the same
records.

## Seeded preferences

Three explicit `Remember...` prompts completed through
`memory_command_preview_call`:

1. Use no more than five concise bullets.
2. Put loss ratio first and total insured value second.
3. Use USD and require explicit human review for adverse recommendations.

The store returned three records, including a consolidated `user_profile`:

> User prefers underwriting summaries formatted in no more than five concise
> bullet points, with loss ratio first and total insured value second. User uses
> USD as their preferred currency. User requires explicit human review for
> adverse recommendations before action.

A brand-new conversation recalled all preferences successfully.

## Architecture boundary

Managed Memory preview does not support VNet integration. The private
`aifoundrydemo3zbz/insurance3zbz` deployment remains network-isolated and does
not carry the managed Memory tool. The public project is a deliberate,
isolated preview showcase.

Recreate or reseed the demo with:

```powershell
python .\scripts\provision_memory_demo.py
```

Reference: [Create and use memory in Foundry Agent Service](https://learn.microsoft.com/azure/foundry/agents/how-to/memory-usage)
