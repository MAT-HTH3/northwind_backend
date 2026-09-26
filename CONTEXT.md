# Northwind Customer Support

Northwind is a utility (electricity and water) whose customers contact support through a chat widget. This context covers deciding whether a customer's request can be resolved by the AI Assistant or must be handed to a Human Agent.

## Language

### People

**Human Agent**:
A Northwind employee who works Support Cases.
_Avoid_: Advisor, specialist, agent (unqualified)

**AI Assistant**:
The AI that talks to customers in the chat widget and resolves Self-service requests.
_Avoid_: Bot, agent, AI agent

### Customer data

**Legacy System**:
One of the four separate systems a Human Agent previously had to check one screen at a time: **Legacy Billing** (bills, charges, rates, payment method), **Metering** (meter readings, actual vs estimated), **CRM** (customer profile and past contacts) and **CaseTrack** (past support cases).
_Avoid_: Backend, source, screen

**Unified Customer History**:
A single merged view of everything known about one customer: the Legacy Systems' data plus the customer's open and closed Support Cases with their Case Outcomes.
_Avoid_: Customer context, 360 view, combined history

### Requests

**Self-service request**:
A customer request the AI Assistant can fully resolve with the data and actions it has, such as explaining a bill or giving a payment date.
_Avoid_: Info request, simple query

**Hand-off request**:
A customer request that needs a Human Agent: a physical repair, a manual billing exception (refund, dispute, payment plan), a submitted meter reading, or the customer explicitly asking for a person.
_Avoid_: Escalation, complex query

### Conversation outcomes

**Auto-resolved**:
A conversation the customer explicitly confirmed was solved by the AI Assistant, with no Support Case opened afterwards in that conversation. Only these count towards handling-cost savings.
_Avoid_: Deflected, closed, self-served

**Handed off**:
A conversation in which a Support Case was opened, regardless of any earlier confirmation from the customer.
_Avoid_: Escalated, transferred

**Unconfirmed**:
A conversation the AI Assistant answered where the customer never confirmed whether it was solved.
_Avoid_: Abandoned, resolved

### Cases

**Support Case**:
The record created when a Hand-off request is handed to a Human Agent, carrying the customer's history and conversations so the customer never has to explain twice. One Support Case can gather several conversations about the same problem. While it is open, the Human Agent owns those conversations and the AI Assistant takes no further action in them.
_Avoid_: Ticket, escalation

**Priority**:
How urgent a Support Case is: high, mid or low. The case's category sets its Priority, and the Priority sets how many days the customer is promised a response within.
_Avoid_: P1/P2/P3, severity

**Case Outcome**:
The Human Agent's written resolution that closes a Support Case (e.g. "Refunded £37.59, corrected bill sent"). It is delivered to the customer outside the chat and remembered in the conversation so the AI Assistant can refer to it later.
_Avoid_: Reply, resolution note
