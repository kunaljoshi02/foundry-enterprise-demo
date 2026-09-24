---
name: adjudication-rationale
description: Produce clause-grounded, regulator-defensible claim adjudication rationales. Use for coverage and settlement analysis by the specialist adjudicator.
---

# Adjudication Rationale

## Required analysis order

1. Confirm the policy form and period.
2. Identify the insuring clause.
3. Test definitions.
4. Test exclusions.
5. Test conditions and conditions precedent.
6. Apply excesses, sub-limits, and limits of indemnity.
7. Identify missing evidence and referral triggers.

## Required output

```text
RECOMMENDATION: COVERED | NOT COVERED | CONDITIONAL | REFER
Confidence: n%

Policy basis
- [Section X.Y - exact title]: quoted wording

Application to facts
- Fact -> clause -> effect

Financial treatment
- Gross covered amount:
- Excess:
- Sub-limit / indemnity limit:
- Recommended net amount:

Evidence and controls
- Missing evidence:
- Human approval required:
```

Never cite a section that was not returned by the policy-search tool. Never
invent wording. If retrieved clauses conflict, return REFER.
