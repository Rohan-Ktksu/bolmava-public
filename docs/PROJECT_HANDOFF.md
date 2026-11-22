# PROJECT HANDOFF: AI-Powered Omnichannel B2B Commerce Platform

**Project status:** Planning completed; ₹0 prototype to be developed  
**Date:** October 26, 2026  
**Budget:** Strictly ₹0 for initial prototype  
**Primary market:** India  
**Objective:** Create an AI-powered B2B marketplace that is accessible even to people with limited literacy or technology experience.

---

## 1. Project Vision

Build a complete AI-powered commerce ecosystem where manufacturers, sellers, distributors, wholesalers, retailers, and buyers can conduct business through three interchangeable channels:

1. AI-powered voice calls
2. WhatsApp text messages and voice notes
3. Web portal with dashboards and AI chat

Users must be able to switch between channels without losing conversations, business information, transaction progress, or reports.

The system should reduce dependence on reading, writing, technical knowledge, complex software, and manual business administration.

**Core philosophy: AI-first, human-backed, financially secure, multilingual, and accessible.**

---

## 2. Problems We Want to Solve

- Small sellers struggle to identify potential customers.
- Manufacturers cannot always find suitable distributors.
- Many business owners don't understand reports, CRMs, marketing, or business analytics.
- People with limited literacy struggle to operate online marketplaces.
- Regional-language barriers prevent commercial transactions.
- Buyers and sellers face fraud, fake accounts, payment disputes, poor quality, and delivery problems.
- Small businesses find quotations, negotiations, accounting, and order management complicated.
- Some manufacturers require advance payments before production.
- Traditional marketplaces often require significant manual interaction.

Our platform should simplify these operations through conversational AI.

---

## 3. Types of Users

### Seller / Manufacturer
- Register a business through conversation.
- Complete assisted verification.
- List and update products through speech or text.
- Find potential buyers and distributors.
- Receive customer enquiries.
- Negotiate quotations.
- Track orders, payments, inventory, and complaints.
- Access AI-generated reports.

### Buyer / Distributor
- Register and verify business identity.
- Describe product requirements by speaking or typing.
- Discover suitable verified sellers.
- Compare prices, quantities, specifications, and delivery dates.
- Request quotations and negotiate.
- Confirm purchase orders.
- Pay through secure authorized channels.
- Track orders and raise disputes.
- Reorder products.

An organization can have both buying and selling capabilities.

### Human Support Agent
- Assist users who cannot understand AI responses.
- Handle calls and conversational handoffs.
- Assist with registration and verification.
- Investigate customer complaints.
- Assist with language misunderstandings.
- Coordinate returns, refunds, and quality issues.

### Finance Administrator
- Review financial exceptions.
- Check advance-payment agreements.
- Review permitted payout requests.
- Approve settlement instructions according to permissions and payment-provider requirements.
- Manage financial disputes and reconciliation.

### Platform Administrator
- Manage organizations and users.
- Supervise marketplace operations.
- Monitor fraud and suspicious accounts.
- Manage human support.
- Review complaints and operational performance.
- Configure user permissions and business rules.

---

## 4. Omnichannel Communication

The three communication channels must use the same backend and database.

**Example:**

Morning: Seller calls AI and registers 500 electrical switches.

Afternoon: Seller asks on WhatsApp whether any buyers are interested.

Evening: Seller checks quotations and sales reports through the web portal.

The same business data must be available in all channels.

Each user can configure:

- Preferred language.
- Preferred communication channel.
- Preferred reporting frequency.
- Preferred explanation complexity.
- Text or audio responses.
- Notification preferences.

Users should be able to change these preferences at any time.

A conversation started in one channel should resume in another after authentication and authorization.

---

## 5. AI Voice Commerce

The AI agent should:

- Understand natural language.
- Identify user intent.
- Ask clarifying questions.
- Extract structured information.
- Register products and business information.
- Search products and suppliers.
- Generate quotations.
- Explain pricing and terms.
- Submit authorized purchase requests.
- Create orders after explicit confirmation.
- Explain payment status.
- Track shipments.
- Register and explain complaints.
- Retrieve and explain reports.
- Transfer the conversation to a human.

Critical amounts, product specifications, and order details must be read back before confirmation.

AI must not invent prices, buyer identities, delivery confirmations, or payment statuses.

---

## 6. Accessibility and Low-Literacy Support

A major differentiation is making the platform usable by people who cannot comfortably read, write, type, or use complicated apps.

Implement:

- Voice-first interactions.
- Simple everyday language.
- One question at a time.
- Optional slow explanations.
- Repetition on request.
- Audio descriptions of reports.
- Examples instead of technical terminology.
- Confirmation of critical details.
- Teach-back questions for financial comprehension.
- Human assistance on demand.
- Basic-phone-compatible design when actual telephony is implemented.

The AI should adapt explanations based on user preference and demonstrated understanding, not stereotypes about education.

---

## 7. Language Requirements

Long-term goal: Support all 22 constitutionally scheduled Indian languages, plus English.

Initial prototype priorities:

- Telugu
- Hindi
- English
- Tamil
- Kannada

Additional languages must be introduced after testing.

Important language issues:

- Dialect differences.
- Code-switching.
- Accents.
- Poor telephone audio.
- Numeric misunderstandings.
- Technical product vocabulary.
- Contract translation.

All commercial transactions must be stored in a canonical structured format, regardless of the language used in conversation.

---

## 8. Seller and Buyer Verification

The AI should guide registration and initiate verification procedures, but must not independently certify identity based solely on speech.

Verification requirements:

- Phone or account ownership.
- Business registration.
- Identity of authorized representatives.
- Business authorization.
- Verified settlement account.
- Suspicious-account detection.
- Risk-based transaction restrictions.

For the ₹0 prototype, verification must use clearly labeled simulated checks or manual demonstration workflows.

Real identity verification requires appropriate trusted services and legal compliance.

Never request banking PINs, passwords, or payment OTPs during AI conversations.

---

## 9. Marketplace and Customer Matching

The marketplace should support:

**Seller-initiated matching:** A manufacturer lists products and requests suitable customers.

**Buyer-initiated matching:** A distributor requests products and the AI identifies sellers.

**RFQ-based matching:** Buyers submit specifications and eligible suppliers provide quotations.

Matching parameters include:

- Product specifications.
- Price.
- Quantity.
- Inventory availability.
- Location.
- Delivery capability.
- Minimum order quantity.
- Business verification.
- Supplier reliability.
- Payment terms.

The system must distinguish potential buyers from verified enquiries and completed sales.

---

## 10. Orders, Negotiations and Contracts

Each transaction should support:

- Buyer enquiry.
- Seller quotation.
- Price negotiation.
- Product and quantity confirmation.
- Delivery agreement.
- Advance-payment agreement.
- Purchase order.
- Payment tracking.
- Shipping and delivery.
- Acceptance or dispute.
- Final settlement and closure.

Contract changes require an updated version accepted by the relevant parties.

A conversational statement must not automatically become a binding order without appropriate confirmation and authentication.

---

## 11. Financial Management

Money is a highly sensitive part of the project.

The platform should eventually support:

- Full payment.
- Partial payment.
- Production advances.
- Milestone payments.
- Partial-order settlements.
- Refunds.
- Settlement approvals.
- Financial disputes.
- Reconciliation.
- Audit records.

Use a regulated payment or banking partner for real fund collection and transfers.

Administrative authority must be subject to enforceable payment rules and partner agreements.

Implement role-based permissions and maker-checker authorization.

An AI agent must never release funds independently.

**For the ₹0 prototype: All money must be simulated. No real payments, lending, escrow, or transfers.**

Potential future partners to investigate include Razorpay and Cashfree, subject to actual supported settlement capabilities and regulatory requirements.

---

## 12. Complaints and Dispute Resolution

Complaint categories:

- Product damaged.
- Wrong product delivered.
- Missing quantity.
- Delivery delays.
- Quality failure.
- Payment not received.
- Refund request.
- Contract misunderstanding.
- Suspicious activity.
- Fraud or impersonation.

The AI should:

1. Authenticate the complainant.
2. Identify the transaction.
3. Register a complaint.
4. Collect available evidence.
5. Notify appropriate parties.
6. Route to a human when required.
7. Track deadlines and status.
8. Explain the outcome in the user's language.
9. Support appeal or further review.

AI cannot arbitrarily determine fault or transfer money.

---

## 13. Human Handoff

AI-to-human escalation is mandatory for:

- Explicit requests to speak with a person.
- Serious financial misunderstandings.
- Fraud and identity concerns.
- High-value disputes.
- Unusual settlement requests.
- Complex negotiations.
- Quality disputes requiring investigation.
- Repeated language comprehension failures.
- Unclear contractual obligations.

The human support agent must receive an authorized summary containing:

- Customer identity and language.
- Relevant conversation history.
- Current request.
- Associated order or complaint.
- Actions already attempted.
- Outstanding issues.

Customers must not be required to restart their explanation.

After resolution, the same conversation can return to AI assistance while retaining its context.

---

## 14. Reports and Business Intelligence

Users should be able to ask:

- How many customers do I have?
- How many orders were placed?
- How much did I sell?
- How much money has actually been received?
- How much is still outstanding?
- Which products sell best?
- Why are my orders delayed?
- Which customers should I contact?
- What complaints are open?
- What should I focus on today?

The AI must retrieve actual database records and explain findings in plain language.

Reports should be accessible through:

- Voice conversations.
- WhatsApp text or audio.
- Web dashboards.

---

## 15. ₹0 Prototype Technology Stack

Use free and open-source tools wherever possible.

**Frontend:** React + Vite  
**Backend:** Python FastAPI  
**Initial database:** SQLite  
**AI engine:** Ollama with a suitable local open-weight model  
**Browser speech:** Browser speech APIs where available  
**Speech recognition fallback:** Local Whisper  
**Text-to-speech:** Browser speech synthesis or free local alternatives  
**WhatsApp:** Meta WhatsApp Cloud API developer testing environment  
**Authentication:** Local prototype authentication with role-based permissions  
**File storage:** Local development storage  
**Hosting:** Developer's computer  
**Payment system:** Simulated transaction ledger  
**Admin portal:** React-based dashboard  
**Code management:** Git and GitHub  

Do not assume every language has acceptable browser voice support.

If local AI is too demanding for the available computer, provide a deterministic mock-agent mode so the full business workflow remains demonstrable without paid APIs.

Production telephony, WhatsApp messaging at scale, cloud hosting, and real financial operations may introduce costs.

---

## 16. Prototype Modules

Build the following modules:

1. Authentication and organization accounts.
2. Seller onboarding.
3. Buyer onboarding.
4. Product and inventory management.
5. AI chat assistant.
6. Browser voice assistant.
7. Buyer-seller matching.
8. Quotations and simulated orders.
9. Simulated payments and admin approvals.
10. Complaint and dispute management.
11. Human handoff queue.
12. Seller, buyer and admin dashboards.
13. Reporting assistant.
14. Communication preferences.
15. WhatsApp developer-mode integration.

All modules should use a shared backend and database.

---

## 17. Suggested Prototype Demo

Create three fictional organizations:

- A manufacturer selling electrical switches.
- A distributor buying in bulk.
- A retailer requesting stock.

Demonstrate the following:

1. Manufacturer registers through the browser voice assistant.
2. Manufacturer creates a product listing.
3. Distributor requests a product.
4. AI matches the distributor with the manufacturer.
5. Distributor receives a quotation.
6. Distributor negotiates terms.
7. Buyer confirms a simulated order.
8. Finance administrator reviews a simulated advance payment.
9. Order progresses to delivery.
10. Buyer raises a quality complaint.
11. AI escalates the complaint to human support.
12. Human agent updates the complaint.
13. Seller asks the AI for their latest business report.
14. Seller switches to WhatsApp or portal and accesses the same record.

This should be demonstrable without real bank accounts, actual products or real-money transfers.

---

## 18. Competitors Reviewed

- IndiaMART — B2B marketplace and lead discovery.
- TradeIndia — Assisted sourcing and payment protection.
- Udaan — B2B wholesale commerce.
- JanAI — Voice-first accessibility and human-assisted services.
- Paisa AI — Voice-based wholesale order processing.
- Awaaz — Voice-oriented local storefront capabilities.
- Sarvam AI — Indian-language AI infrastructure.
- ONDC — Potential future commerce-network integration.

Our intended differentiation is the combination of voice-first accessibility, genuine buying and selling, multilingual explanations, human support, and transparent financial controls.

---

## 19. Initial Target Market

For the first prototype, choose a single B2B category instead of attempting all industries.

Candidate categories:

- Electrical products.
- Electronic components.
- Packaging materials.
- Small manufacturing supplies.

Suggested initial pilot after development:

- 20 sellers.
- 20 buyers or distributors.
- Telugu-first operations.
- Manually supervised trade transactions.
- Structured usability and trust testing.

---

## 20. Current Development Status

**Completed:** Concept exploration, requirements discussion, competitor research, initial architecture, operating model and zero-cost prototype approach.

**Not yet completed:** Actual source code, database, interfaces, integrations, deployment, and technical testing.

No production infrastructure or payment systems have been created.

---

## 21. Important Non-Negotiable Requirements

- ₹0 initial prototype budget.
- No paid APIs required for core demonstration.
- Open-source technology preferred.
- Voice, WhatsApp and web access.
- Shared user accounts and business information.
- Strong accessibility.
- Explicit purchase confirmation.
- Human review for sensitive financial actions.
- Financial simulation only during prototyping.
- No fabricated business or payment data presented as real.
- No identity verification based solely on voice.
- Secure role-based permissions.
- Complaint and dispute workflows.
- Privacy and consent.
- Modular architecture that can expand later.

---

## 22. Next Task for the Development Assistant

Create a detailed technical specification and begin implementing the ₹0 working prototype.

Start with:

1. Project folder structure.
2. Backend architecture.
3. Database schema.
4. Frontend page structure.
5. API contracts.
6. Authentication and role model.
7. Shared conversation and channel-state architecture.
8. Voice-agent workflow.
9. Simulated transaction and admin approval engine.
10. Local setup and run instructions.

Build incrementally, starting with the shared backend, working seller registration, product catalog, buyer discovery and browser-based conversation.

Use mock data and simulated integrations where needed so every critical workflow can be demonstrated without payments or subscriptions.

**Final goal:** A functional, accessible, multilingual AI B2B marketplace prototype in which sellers, buyers and distributors can conduct business using voice, chat and a web portal, with human escalation and safe financial controls.
