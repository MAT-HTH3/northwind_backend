---
status: superseded by ADR 0004
---

# Every submitted meter reading goes to a Human Agent

A meter reading submitted in chat is always a Hand-off request. It is recorded with status `awaiting_review`, a "Meter reading review" Support Case is opened, and a Human Agent decides whether the bill changes. The AI Assistant never re-prices a bill and never promises a corrected amount. This is a deliberate departure from industry practice: UK suppliers normally accept self-reads automatically, check them against expected usage, and re-bill without a person. We considered that approach (automatic acceptance with a plausibility check and a simulated bill run) and a middle ground (showing a provisional amount without applying it). We chose the simplest option because we don't want a customer-supplied number to change a bill without a person checking it, and because the automatic path needed a re-billing loop we don't own.

## Consequences

- Each reading costs a Human Agent's time, so readings don't count towards the handling-cost savings. Revisit this ADR if readings become a large share of Support Cases.
- The frontend's `MeterReadingReceipt` has no revised amount, and its copy must not imply the bill has already changed.
