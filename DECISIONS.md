# Resolved Ambiguities & Product Decisions (`DECISIONS.md`)

Building enterprise-grade software means addressing real-world irregularities. This document outlines every ambiguity resolved, our design justifications, what was handled vs ignored, and questions for the Product Manager.

---

## 1. Ambiguities Resolved

### A. Non-Calendar Utility Billing Cycles
*   **The Ambiguity**: Billing periods span arbitrary dates (e.g., April 18 to May 17), but ESG reporting is aggregated strictly by calendar month.
*   **The Decision**: We implemented a **linear daily pro-rating splitter**. For a 30-day billing cycle spanning 12 days in April and 18 days in May, the usage and charges are split $12/30$ and $18/30$ respectively. We generate two separate activity database rows, each referencing the original invoice raw record. This ensures precise, auditable monthly reporting.

### B. Incomplete Travel Segment Logs (Missing Flight Mileages)
*   **The Ambiguity**: Client travel agencies (Concur/Navan) often omit flight mileages, providing only airport codes (e.g., "JFK", "LHR").
*   **The Decision**: We seeded a master directory of global airport hubs (`AirportLookup`) with exact latitude/longitude coordinates. If the flight record has `distance_km = 0` or missing, our engine dynamically executes the **Haversine great-circle distance formula** to calculate distance. If an IATA code is unmapped, we fallback to a standard short/long-haul segment (1200 km) and flag it as a warning so the analyst can correct it.

### C. Inconsistent Units in ERP Exports (German vs English)
*   **The Ambiguity**: SAP materials and unit fields can contain mixed German or English abbreviations (e.g., `L`, `LTR`, `LITER`, `TO`, `TONNE`, `KG`, `GAL`, `GALLON`).
*   **The Decision**: We wrote a **tolerant unit normalizer** in `parsers.py` that translates all common spelling permutations into standard metrics. It also performs mathematical metric scaling:
    *   `GAL` is converted to `Liters (L)` (multiplied by `3.78541`).
    *   `TO` is converted to `Kilograms (KG)` (multiplied by `1000`).
    Every unit conversion triggers an automated warning trace logged directly on the row to guarantee audit visibility.

### D. Ingestion Error Representation
*   **The Ambiguity**: When an uploaded file contains structural syntax errors or bad data values, how do we surface it?
*   **The Decision**: Instead of rejecting the entire file or failing silently, we implemented a **Partial Success Ingestion Flow**. Successful rows are processed normally. Failed rows are logged as raw errors, and a dummy row of status `ERROR` is inserted into the analyst workspace. This allows the non-technical auditor to see the exact row number and error trace (e.g., `Unable to parse date string: 'INVALID_DATE'`) directly in their dashboard.

---

## 2. Scope of Ingested Reality (Subsets Handled vs Ignored)

### What We Handled:
1.  **SAP MSEG/MKPF Material Document Structure**: German headers, posting date parsing, plant mapping, metric conversions, and fuel-combustion mapping.
2.  **PG&E Green Button Portal CSV**: Billing cycles, pro-rating, electricity spikes, and meter overlaps.
3.  **Concur Travel Exports**: Segment classifications (Flights, Hotels, Ground Transport), airport coordinates calculations, hotel night overrides, and spend-based taxi mileage estimation.
4.  **Auditor Action Panel**: Complete edit drawer, strict change justification logs, and cryptographic-style auditing row locking.

### What We Ignored:
1.  **Live SAP OData RFC Connections**: Real SAP environments use highly secure OData web services or BAPI calls. For this prototype, we focused on processing the flat-file CSV dumps (AL11 exports) which represent 90% of actual company onboarding files.
2.  **Live FX Multi-Currency Convertors**: Spend values in SAP or Concur are converted using standard predefined factors if currencies differ, ignoring real-time foreign exchange market fluctuations.
3.  **Electricity Grid Peak Demand Charges**: Real utility bills charge separate demand rates per peak-kW. We ignored demand tariffs, focusing purely on total active consumption (`kWh`) and pro-rated charges for carbon emissions.

---

## 3. Clarifying Questions for the Product Manager

> [!IMPORTANT]
> **Questions that will guide the production release:**
> 1.  **Unmapped Plant Code Escalation**: If an SAP export contains a new plant code (`WERKS`) not pre-registered in our master Plant directory, should the system immediately reject the file, or is our current design of processing it with a "Default Region Grid Factor" and flagging it as `FLAGGED` the preferred flow?
> 2.  **EEIO Spend-Based Data Sourcing**: For procurement-based Scope 3 calculations, does the client wish to import standard EPA EEIO spend coefficients, or will they provide a custom company-wide spend-to-CO2e lookup directory?
> 3.  **Audit Lock Override Policy**: Once an analyst locks a row for audit, should there be any "Auditor Super-Admin" role capable of unlocking it, or must it remain 100% immutable as required by SEC/SBTi audit guidelines?
