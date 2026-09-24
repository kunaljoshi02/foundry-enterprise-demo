---
name: underwriting-appetite
description: Apply Contoso underwriting appetite and referral rules to submission summaries. Use when recommending accept, refer, decline, terms, or information requirements.
---

# Underwriting Appetite

## Decision classes

- **ACCEPT** - standard appetite; no material adverse feature.
- **ACCEPT WITH TERMS** - within delegated authority with explicit excess,
  limit, warranty, or pricing adjustment.
- **REFER** - outside delegated authority, incomplete evidence, conflicting
  signals, or material uncertainty.
- **DECLINE** - only where an explicit appetite rule applies; always require
  human approval.

## Risk lenses

Assess:

1. exposure and hazard;
2. five-year frequency and severity;
3. trend and large-loss drivers;
4. controls and risk improvements;
5. data quality;
6. aggregation and catastrophe exposure;
7. conduct and fairness concerns.

## Authority and OBO

Treat tool results as scoped to the signed-in user's permissions. Do not infer
or reveal data that the OBO tool withheld. State which user role was applied.
A junior underwriter must not receive restricted loss narratives or full
financial detail.

Return the decision, confidence, rationale, proposed terms, missing evidence,
and required approver.
