# The model sees only the customer's words

Gemini receives what the customer types and the AI Assistant's own general replies, and nothing else. No names, account numbers, balances, readings, bills, cases or other records go into any prompt, tool result or history that reaches the model. Tools return a short status to the model ("bill shown to the customer") and the full record to the widget as the card, using LangChain's `content_and_artifact`. Figures appear only on cards. Card text, change reasons and Support Case summaries are written by code from templates.

The competition rules do not require this, since they only forbid data-pack content in AI systems and our demo data is invented. We chose it because Northwind itself bans putting its data into AI tools, so a design where the model reads customer records would need a policy exception before it could ship. This design can ship under Northwind's current policy. A side effect: the model cannot misquote a balance, because it never states one.

## Considered options

- **The model reads invented records (what we had built first).** Richer answers, such as "your payment is due 5 October", but the production version conflicts with Northwind's AI policy.
- **The model reads only derived, non-identifying facts.** Rejected because the line between "derived" and "record" is hard to draw and hard to defend.

## Consequences

- The Categorizer classifies from the conversation text alone.
- The Auto-Resolver cannot state dates, amounts or case status in words. A card or a code-written template has to carry them.
- The Unified Customer History is still built every turn. Code uses it for cards, templates and the Human Agent's view, but it never reaches the model.
