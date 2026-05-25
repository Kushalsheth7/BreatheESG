# Architectural Trade-offs (`TRADEOFFS.md`)

In engineering a production-grade prototype under strict timelines, we deliberately chose to optimize for **ingestion robustness, database integrity, and analyst workspace clarity**. This document details three features we deliberately omitted, our design rationale, and our long-term roadmap recommendation.

---

## 1. Omission: PDF Invoice Optical Character Recognition (OCR) Parser
*   **What was requested**: Utility bills often arrive as PDF invoices or portal scrapes.
*   **What we built instead**: A structured, PGE-compliant **Utility Portal CSV Ingestion Parser**.
*   **The Rationale**: Implementing a local PDF parser using OCR (e.g., Tesseract) or a machine-learning text-extraction model is highly fragile. Different utility providers (PG&E, National Grid, ConEd) alter their document templates frequently, leading to field misalignment and ingestion failures during auditor validation. A failed OCR parse can swallow critical demand charges or read dates, which is unacceptable for audit.
*   **The Trade-off**: Standardizing on the official **Green Button XML/CSV portal export** ensures 100% structured data accuracy, zero parse slips, and immediate compliance.
*   **Future Production Recommendation**: Implement an asynchronous document processor using **AWS Textract** or **Document AI**, linked to a human-in-the-loop validation queue for anomalous pdf invoices.

---

## 2. Omission: Automated Live Grid API Integrations (eGrid/ElectricityMap)
*   **What was requested**: Grid electricity emission factors change dynamically by hour, region, and tariff structures.
*   **What we built instead**: A robust **Database-Backed PlantLookup Directory**.
*   **The Rationale**: Integrating live API feeds (e.g., tomorrow.io or Tomorrow's ElectricityMap API) creates external, fragile network dependencies. If their servers experience downtime, client file ingestions will crash. Furthermore, third-party APIs frequently deprecate schemas or rate-limit requests. For an auditor, an emission factor sourced from an external API that changes retroactively is a major red flag.
*   **The Trade-off**: By utilizing a static database-seeded lookup directory (`PlantLookup`), we guarantee that grid coefficients are predictable, historical, stable, and completely transparent. If an auditor asks why a plant used a factor of `0.345`, the analyst can point directly to the audited Plant Directory.
*   **Future Production Recommendation**: Schedule a nightly background job (`celery cron`) that pulls official eGRID (US EPA) or national grid emission directories and writes them to the database, ensuring coefficients remain up-to-date while maintaining internal database stability.

---

## 3. Omission: Full RBAC User Authentication & OAuth/SAML SSO
*   **What was requested**: Multi-tenancy and audit tracking (which auditor signed off and when).
*   **What we built instead**: Logical **Tenant Database Schemas** and a simple **Auditor Name Session Input** in the dashboard header.
*   **The Rationale**: Writing full login pages, password hashing, JWT access/refresh tokens, and multi-factor authentication (MFA) redirects adds substantial boilerplate code. It drains valuable development time away from solving the hard problems—calendar month splitting, Haversine routing, unit conversions, and auditor adjustment tracking.
*   **The Trade-off**: We implemented deep multi-tenant relationships (`Tenant` Foreign Keys) and transaction-atomic `AuditLog` mapping. The auditor inputs their signature in the workspace header, which is automatically captured as the `approved_by` and `changed_by` value. This fully demonstrates data isolation and trace-logging while keeping the prototype highly functional and easy to run immediately.
*   **Future Production Recommendation**: Integrate a standardized OAuth2/SAML SSO service like **Auth0**, **Okta**, or Django's standard social auth framework to delegate user management to enterprise corporate directories.
