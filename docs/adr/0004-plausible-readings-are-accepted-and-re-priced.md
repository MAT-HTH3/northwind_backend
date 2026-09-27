# Plausible meter readings are accepted and re-priced by code

Supersedes ADR 0002. A Customer Reading is checked in code against the last reading on the meter. If it is plausible (more than 0 and at most 2,000 kWh above the last reading), it is accepted and the bill is re-priced from the actual usage. This is a Self-service request and no Human Agent is involved. If it is implausible, it is saved as `needs_review` and becomes a Hand-off request: a Support Case for a Human Agent to check. This is how UK suppliers work: automatic re-billing from self-reads, with people for the exceptions.

We first chose "every reading goes to a Human Agent" (ADR 0002) to keep things simple and because nobody could verify a customer's number. We changed our minds for three reasons: the frontend's receipt card and demo script were built for automatic re-pricing, every accepted reading is a chat that can be Auto-resolved instead of a Human Agent case, and the risky readings (the ones that fail the check) still reach a person.

## Consequences

- The re-priced amount is calculated by code from the tariff and the usage, never by the model (ADR 0003).
- The plausibility bounds are demo values, to be tuned with the metering team.
