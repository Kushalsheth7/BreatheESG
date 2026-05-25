# Data Model Specification & Design Rationale (`MODEL.md`)

This document details the database architecture of the Breathe ESG prototype. It has been engineered to serve enterprise clients with strict security, transparency, multi-tenancy, and audit requirements.

---

## 1. Entity Relationship Overview

The system is built on **8 Core Entities** within SQLite, representing a relational mapping of activity logs, master directories, and compliance histories:

```mermaid
classDiagram
    class Tenant {
        +id: int
        +name: varchar
        +created_at: datetime
    }
    class PlantLookup {
        +id: int
        +tenant_id: int
        +plant_code: varchar
        +name: varchar
        +city: varchar
        +country: varchar
        +grid_emission_factor: decimal
    }
    class AirportLookup {
        +iata_code: varchar (PK)
        +airport_name: varchar
        +city: varchar
        +country: varchar
        +latitude: decimal
        +longitude: decimal
    }
    class EmissionFactor {
        +id: int
        +scope: varchar
        +category: varchar
        +factor: decimal
        +unit: varchar
        +description: text
    }
    class IngestionJob {
        +id: int
        +tenant_id: int
        +source_type: varchar
        +status: varchar
        +file_name: varchar
        +row_count: int
        +success_count: int
        +error_count: int
        +timestamp: datetime
    }
    class RawSourceRecord {
        +id: int
        +ingestion_job_id: int
        +tenant_id: int
        +row_index: int
        +raw_data: json
        +processed_status: varchar
        +error_message: text
    }
    class NormalizedActivity {
        +id: int
        +tenant_id: int
        +ingestion_job_id: int
        +raw_record_id: int
        +scope: varchar
        +category: varchar
        +quantity: decimal
        +unit: varchar
        +co2e_kg: decimal
        +start_date: date
        +end_date: date
        +plant_code: varchar
        +origin_airport: varchar
        +destination_airport: varchar
        +cabin_class: varchar
        +hotel_nights: int
        +status: varchar
        +validation_issues: json
        +original_data: json
        +is_locked: boolean
        +approved_by: varchar
        +approved_at: datetime
    }
    class AuditLog {
        +id: int
        +normalized_activity_id: int
        +changed_by: varchar
        +changed_at: datetime
        +field_name: varchar
        +old_value: text
        +new_value: text
        +reason: text
    }

    Tenant "1" --> "0..*" PlantLookup
    Tenant "1" --> "0..*" IngestionJob
    Tenant "1" --> "0..*" NormalizedActivity
    IngestionJob "1" --> "0..*" RawSourceRecord
    IngestionJob "1" --> "0..*" NormalizedActivity
    RawSourceRecord "1" --> "0..*" NormalizedActivity
    NormalizedActivity "1" --> "0..*" AuditLog
    PlantLookup "0..1" --> "0..*" NormalizedActivity : plant_code
```

---

## 2. Key Architecture Pillars

### A. Multi-Tenancy Architecture
Multi-tenancy is handled via a **logical database-level isolation** scheme. The `Tenant` table serves as the root container. The tables `PlantLookup`, `IngestionJob`, `RawSourceRecord`, and `NormalizedActivity` are associated directly via a Foreign Key to the `Tenant` entity.
- All backend query sets are strictly scoped by the `tenant` parameter (e.g. `NormalizedActivity.objects.filter(tenant_id=tenant_id)`). This guarantees that client analysts never leak data to other organizations.

### B. Scope 1 / Scope 2 / Scope 3 Classification
Emissions are structured strictly per the GHG Protocol standard:
- **Scope 1 (Direct Emissions)**: Ingested from SAP fuel receipts (e.g. Stationary Diesel Combustion). Base normalized unit is Liters (`L`).
- **Scope 2 (Indirect Emissions)**: Pro-rated grid electricity from utility portal bills. Base normalized unit is kilowatt-hours (`kWh`). Grid coefficients are dynamically mapped based on facility Plant coordinates/regions.
- **Scope 3 (Other Indirect Emissions)**: Travel segment details (Economy/Business Flights, Taxi travel, Train rides, and Hotel nights) as well as general supply procurement records. Base normalized units are Passenger-Kilometers (`p-km`), Room-Nights, and Spend Currencies.

### C. Source-of-Truth Tracking & Archival
To remain highly compliant for third-party auditing, every normalized activity row is traceable directly back to its origin:
1. `RawSourceRecord` contains a `raw_data` JSON field which holds the exact, unmodified key-value pairs representing the raw imported CSV row before any transformations were made.
2. `NormalizedActivity` maintains a foreign key to `RawSourceRecord` and `IngestionJob`. If an analyst clicks into any row, they can inspect the original raw payload immediately inside the React drawer, creating an absolute audit trail.

### D. Unit Normalization Engine
Raw client files arrive with arbitrary units (e.g., German/English, imperial/metric).
- The `parsers.py` normalize units into canonical units (`L` for liquids, `KG` for weight, `kWh` for energy, `p-km` for flights, etc.) before computing carbon values.
- **Unit Conversions Built-in**:
  - Gallons (`GAL`) -> Liters (`L`) (multiplier `3.78541`)
  - Tons (`TO`) -> Kilograms (`KG`) (multiplier `1000`)
  - Liters/Tons German labels (`LITER`, `TONNE`) -> canonical system keys.

### E. Calendar Month Splitting & Interpolation
Utility billing cycles rarely align neatly with calendar months (e.g. May 12 to June 11). For monthly reporting, our system pro-rates utility records:
1. `get_days_per_month` dynamically identifies the calendar months crossed by the billing period.
2. Pro-rates the quantity consumed and total charges linearly based on the exact day counts falling within each month.
3. Creates separate, distinct `NormalizedActivity` rows in the database, maintaining full trace links to the original single `RawSourceRecord`.

### F. Strict Change Auditing & Locking
Compliance requires that data is immutable once submitted for audit, but adjustable before:
- **Locking**: When an analyst clicks "Lock & Sign-off", `is_locked` is set to `True`, freezing the database record. Subsequent update calls return a 400 Bad Request.
- **Audit Logs**: If an adjustment is made to an unlocked row (e.g. corrected quantity), a transaction-atomic `AuditLog` entry is logged. It stores the auditor's name, timestamps, exact field modified, pre-change value, post-change value, and a **strict manual justification explanation**.
