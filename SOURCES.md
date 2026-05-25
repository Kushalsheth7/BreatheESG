# Real-World Data Sources Research (`SOURCES.md`)

This document presents our domain research, implementation details, sample data justifications, and real-world failure cases for the three company emissions data sources.

---

## 1. SAP ERP: Fuel and Procurement (Scope 1 / Scope 3)

### A. Real-World Format Researched
In corporate enterprise environments, SAP fuel and procurement logs are pulled from the **Material Management (MM)** module. Specifically, standard transactional tables are joined:
- **MKPF** (Material Document Header): Yields `MANDT` (Client ID), `MBLNR` (Material Document Number), and `BUDAT` (Posting Date in Document).
- **MSEG** (Material Document Segment): Yields `ZEILE` (Item Number), `MATNR` (Material Number), `MAKTX` (Material Description), `MENGE` (Quantity), `MEINS` (Base Unit of Measure), `WERKS` (Plant/Factory Code), and `LIFNR` (Vendor ID).
- **BSEG / RSEG** (Accounting/Invoice items): Yields `DMBTR` (Amount in Local Currency) and `WAERS` (Currency Key) for spend-based calculations.

Enterprise clients export this data via scheduled ABAP reports to AL11 application folders as flat CSVs.

### B. What We Learned & Handled
1.  **Inconsistent Date Formats**: Enterprise postings utilize dates ranging from traditional SAP strings (`YYYYMMDD`), German style (`DD.MM.YYYY`), to US formats (`MM/DD/YYYY`). We built a **multi-format date parsing pipeline** that tolerates and resolves all of them.
2.  **German Column Headers**: SAP retains German database abbreviations (`BUDAT`, `MENGE`, `WERKS`). Our parser maps these fields natively, eliminating client friction.
3.  **Cryptic Plant Codes**: Codes like `DE01` or `US02` are meaningless. We introduced the `PlantLookup` directory to resolve plant codes to physical regions and dynamically map their localized Grid Emission Factors.
4.  **Unit Normalization**: Translates German units (e.g., `LITER` -> `L`, `TO` -> `KG` scaling by 1000) and converts US Gallons (`GAL`) to Liters (`L`).

### C. Sample Data Justification & Breakages
-   **Our Sample Data**: Includes mixed-format dates (`20260501`, `05/10/2026`, `15.05.2026`), German/English units (`L`, `LITER`, `GAL`, `TO`), an unregistered plant code (`DE99`) to trigger auditor warning flags, and an invalid quantity row (`BAD_QTY`) to verify partial error handling.
-   **What would break in real deployment**: Custom SAP configurations often modify standard fields. If a client's ABAP developer exports a non-standard delimiter (e.g., semi-colons `;` instead of commas `,`) or changes standard header casing (e.g., `Menge` instead of `MENGE`), positional parsers will break. Our parser handles header stripping and case normalization to mitigate this.

---

## 2. Utility Data: Grid Electricity (Scope 2)

### A. Real-World Format Researched
Utility data is typically acquired via the utility's online portal using the standardized **"Green Button: Download My Data"** interface (backed by the ESPI XML/CSV standard).
The resulting CSV export (e.g., PG&E or ConEd) contains:
- `Account_Number`: Client service billing ID.
- `Meter_Number`: The physical smart meter identifier.
- `Billing_Start_Date` & `Billing_End_Date`: The billing cycle duration.
- `Usage_kWh`: Active energy consumption in Kilowatt-hours.
- `Tariff_Name` / `Rate_Schedule`: e.g. Commercial Time-of-Use (`TOU-A`).
- `Total_Charges_USD`: Total billing spend.

### B. What We Learned & Handled
1.  **Non-Calendar Alignment**: Invoices cover billing periods spanning multiple months (e.g., May 12 to June 11). For carbon auditing, emissions must be tracked strictly by calendar month. We implemented a **daily linear pro-rating algorithm** that splits consumption and charges across calendar months, creating separate database activity records traceable to the parent record.
2.  **Billing Overlaps**: Multiple invoices can accidentally overlap for the same physical meter (indicating double-billing or incorrect accounting). We implemented an **Active Period Overlap Detection** that flags overlapping date ranges for review.
3.  **Excessive Load Spikes**: Facility errors or equipment failures cause massive consumption surges. We built a spike-threshold check flagging any monthly pro-rated usage $> 30,000$ kWh.

### C. Sample Data Justification & Breakages
-   **Our Sample Data**: Features non-calendar date ranges, overlapping dates for meter `MTR-98234-A` to trigger duplicate warnings, an extreme industrial consumption spike (45,000 kWh) for plant `IN03`, and an invalid date row.
-   **What would break in real deployment**: Multi-facility enterprises often have hundreds of active accounts and meters. If a meter is physically swapped by the utility provider, the meter ID changes mid-cycle. Without a robust historical meter-to-facility mapping directory, data ingestion will fail or assign carbon footprint values to the wrong plants.

---

## 3. Corporate Travel: Flights, Hotels, Ground (Scope 3)

### A. Real-World Format Researched
Corporate travel platforms (e.g., SAP Concur, Navan, TripActions) capture travel bookings and expense reports. A typical expense transaction export captures:
- `Booking_ID` / `Expense_ID`: Unique reservation key.
- `Passenger_Email`: Employee traveler key.
- `Trip_Start_Date` & `Trip_End_Date`: Duration of journey.
- `Category`: `Flight`, `Hotel`, or `Ground` (Taxi/Train).
- `Origin` & `Destination`: IATA Airport Codes (e.g., `JFK`, `LHR`).
- `Cabin_Class`: `Economy`, `Business`, or `First` class.
- `Distance_km` / `Distance_Miles`: Flight segment distance.
- `Nights`: Number of hotel nights booked.
- `Spend_Amount` & `Spend_Currency`: Cost of transport or lodging.

### B. What We Learned & Handled
1.  **Missing Flight Mileages**: Platforms frequently capture *only* IATA codes, leaving distance blank. We seeded an `AirportLookup` directory containing global airport GPS coordinates and integrated a **Haversine great-circle distance algorithm** to calculate mileage dynamically.
2.  **Class-Based Emission Variations**: Business and First Class seats have a significantly larger spatial footprint on flights, translating to higher Scope 3 multipliers. Our parser maps travel category classes (`Economy` vs `Business` vs `First`) to their corresponding standard EPA/DEFRA emission factors.
3.  **Missing Hotel Nights**: Inferred dynamically by calculating the delta between `Trip_End_Date` and `Trip_Start_Date`.
4.  **Missing Ground Distances**: Estimated mathematically based on taxi fare spends (assuming a conservative $1.5$ km per USD spent).

### C. Sample Data Justification & Breakages
-   **Our Sample Data**: Flight from JFK to LHR with missing distance (triggers Haversine coordinate calculation), flight SFO to JFK in Business class, hotel stay with missing room-nights (triggers date-delta calculation), taxi ride with missing mileage (triggers spend estimation), a future flight segment to test chronological anomaly validation, and a electric train segment.
-   **What would break in real deployment**: Multi-leg flight segments (e.g., NY to London, London to Paris, Paris to Tokyo, all booked under a single invoice) create complex circular routes. Parsing standard origin/destination columns without an active segment-leg sequencer will under-report flight mileage. Furthermore, hotel stays in regions with highly unique carbon grids (e.g. low-carbon nuclear France vs coal-heavy Germany) require regional hotel factors, whereas typical CSV dumps do not specify the hotel's geographic coordinates.
