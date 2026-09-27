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
A customer request the AI Assistant can fully resolve with the data and actions it has, such as explaining a bill, giving a payment date, or accepting a plausible Customer Reading.
_Avoid_: Info request, simple query

**Hand-off request**:
A customer request that needs a Human Agent: a physical repair, a manual billing exception (refund, dispute, payment plan), a Customer Reading that fails the plausibility check, or the customer explicitly asking for a person.
_Avoid_: Escalation, complex query

**Customer Reading**:
A meter reading the customer types in chat. If it is plausible for their meter, it is accepted and the bill is re-priced by code. If not, it goes to a Human Agent for review.
_Avoid_: Submitted reading, self-read

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

**Triage Rules**:
The points-based scorecard that sets a Support Case's Urgency, queue and due date from its facts (category, the customer's words, vulnerability, repeat contact, disputed amount, transfers). The same rules run on the agent desk and in the backend, so both always agree.
_Avoid_: Routing table, AI triage

**Urgency**:
How urgent a Support Case is: High, Medium or Low. The Triage Rules set it, a Human Agent can override it, and it sets how many days the customer is promised a response within. Stored in the API as P1 (High), P2 (Medium) and P3 (Low).
_Avoid_: Priority, severity, high/mid/low

**Case Status**:
Where a Support Case is in its work: New, In progress, Waiting for customer (all open, so its conversations are held) or Resolved (closed). Changing a Resolved case back to another status reopens it, but does not hold its conversations again.
_Avoid_: Open/closed as statuses, state

**Case Outcome**:
The reason a Human Agent picks when resolving a Support Case: information only, bill explained, bill corrected, refund issued, field visit, or other. It is the only part of the resolution the customer's side can learn, through a line written by code.
_Avoid_: Resolution note, reply

**Feedback Note**:
Tags and a written note a Human Agent adds to a Support Case, for other Human Agents only. Shown verbatim on the agent desk; never shown to the customer and never sent to the model.
_Avoid_: Comment, internal note, agent summary
