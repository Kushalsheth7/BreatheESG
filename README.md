# 🛡️ Breathe ESG - Ingestion & Analyst Review Dashboard

This repository contains a production-grade prototype built in **Django REST Framework** and **React Vite** that solves the hardest part of carbon accounting: **ingesting, normalizing, and auditing highly inconsistent corporate activity data.**

Sustainability and carbon footprint logs rarely arrive in clean shapes. Instead, they are scattered across German SAP exports, PGE electricity portal cycles, and Concur travel segment bookings. This platform acts as an automated normalization engine and an executive-grade glassmorphic workspace for sustainability auditors.

---

## 📖 How It Works: The "Customs & Sorting Office" Analogy

To understand all the complex parts of this codebase, imagine you are running a **High-Security International Carbon Customs & Sorting Post Office**:

1.  **The Messy Raw Cargo (Ingested Files)**: 
    *   **SAP MM ERP Packages**: Arrive written in German database abbreviations (`MENGE` for quantity, `WERKS` for plant codes), mixed currencies, and inconsistent units (like `GAL`, `LITER`, `TO`).
    *   **Utility Bill Packages**: Arrive as giant packages covering random billing dates (e.g., May 12 to June 11) that don't fit neatly into standard, calendar-clean monthly mailboxes.
    *   **Travel Platform Packages**: Arrive as letters saying, *"Employee flew JFK to LHR in Business Class,"* but omit flight mileage, hotel nights, and taxi distance values.
2.  **The Conveyor Belt & Sorters (Our Django Backend)**:
    *   **The SAP Translator**: Automatically translates German headers, standardizes inconsistent spelling configurations, and scales metrics mathematically (converts Gallons to Liters, scales Metric Tons to Kilograms).
    *   **The Utility Splitter (Linear Interpolation)**: Uses a digital daily knife to cut billing packages proportionally (e.g., 20 days of power consumption go into May's slot, 10 days go into June's slot) to ensure calendar-month alignment.
    *   **The GPS Travel Calculator (Haversine & Class Multipliers)**: Queries a coordinates database of global IATA hubs, plots origin/destination coordinates, and runs a mathematical ruler (**the Haversine formula**) to compute precise flight distances. If the ticket says "Business Class," it scales the carbon footprint since business class seats occupy more spatial volume on airplanes!
3.  **The Auditor Review Counter (Our React Dashboard)**:
    *   Surfaces processed activities in a glowing glassmorphism table. 
    *   🟢 **Approved**: Signed off and locked in a secure compliance vault.
    *   🟡 **Pending**: Awaiting analyst validation.
    *   🟠 **Flagged**: Triggered automated warnings (large consumption spikes, duplicate billing dates, unmapped plant codes).
    *   🔴 **Error**: Catch-all for damaged data (e.g., bad quantity values or corrupt dates).
4.  **The Safe & Audit Logs**:
    *   If an analyst adjusts a row (e.g., updates a quantity), they must enter their name and provide a **compulsory written justification** that is logged transaction-atomically.
    *   Once stamped **"Lock & Sign-off"**, the record is cryptographically locked (`is_locked = True`), frozen forever, and ready for SEC/SBTi audit scrutiny.

---

## 🛠️ Project Directory Structure

```text
├── backend/
│   ├── breathe_esg/        # Django Core (settings, URLs, WSGI)
│   ├── api/
│   │   ├── models.py       # Multi-tenant and compliance database models
│   │   ├── parsers.py      # Core parser engine (Haversine, date pro-rating, unit scales)
│   │   ├── serializers.py  # DRF serializers mapping entities
│   │   ├── views.py        # Upload views, dashboard metrics, and seeding scripts
│   │   └── urls.py         # Sub-routing for REST endpoints
│   ├── db.sqlite3          # SQLite Database
│   ├── requirements.txt    # Django dependencies
│   ├── verify_ingestion.py # CLI Parser Validation System
│   └── test_api_endpoints.py # Automated HTTP endpoint test suite
│
├── frontend/
│   ├── dist/               # Compiled assets bundle
│   ├── src/
│   │   ├── App.jsx         # Dashboard workspace & slide drawer
│   │   ├── index.css       # Premium custom HSL CSS style tokens
│   │   └── main.jsx        # React DOM entrypoint
│   ├── index.html          # Web view page template
│   ├── vite.config.js      # Vite compilation tools
│   └── package.json        # Node dependency schema
│
├── mock_data/              # Realistic mock exports for trial runs
│   ├── sap_fuel_procurement.csv
│   ├── utility_electricity.csv
│   └── travel_concur.csv
│
├── MODEL.md                # Multi-tenancy database structures and design rationale
├── DECISIONS.md            # Resolved ambiguities, subsets handled, and PM questions
├── TRADEOFFS.md            # Explains the three deliberately omitted features
└── SOURCES.md              # Research summary of database tables and fail vectors
```

---

## 🚀 How to Run the Project Locally

Follow these quick commands to spin up the full platform on your Windows machine:

### 0. Clone the Repository
In your terminal, run the following git command to clone the repository:
```bash
git clone https://github.com/Kushalsheth7/BreatheESG.git
cd BreatheESG
```

### 1. Run the Django REST Backend
Open your terminal (PowerShell or standard command prompt), navigate into `/backend`, and execute:

```powershell
# 1. Navigate to backend directory
cd backend

# 2. Create the Python virtual environment
python -m venv venv

# 3. Activate the virtual environment
.\venv\Scripts\Activate.ps1

# 4. Install backend requirements
pip install -r requirements.txt

# 5. Run database migrations to prepare schemas
python manage.py makemigrations api
python manage.py migrate

# 6. Start the local API development server on Port 8000
python manage.py runserver 8000
```
*The backend REST API is now live at [http://127.0.0.1:8000](http://127.0.0.1:8000).*

### 2. Run the React Dev Server
Open a **new, secondary terminal**, navigate into `/frontend`, and execute:

```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install React and dashboard dependencies
npm install

# 3. Start the Vite development server
npm run dev
```
*The interactive dashboard workspace is now live at [http://localhost:5173](http://localhost:5173).*

---

## 🧪 Automated Testing & Seeding

We have built two script entrypoints inside `/backend` so you can verify and bootstrap the database instantly in your terminal:

*   **To run the CLI parser verification system**:
    ```bash
    .\venv\Scripts\python verify_ingestion.py
    ```
    *This runs a complete local simulation, migrating, seeding factors, and printing out a beautiful table showing units standardizing, pro-rated calendar splits, and Haversine flight paths.*

*   **To run the HTTP Endpoint Integration tests**:
    ```bash
    .\venv\Scripts\python test_api_endpoints.py
    ```
    *This simulates actual browser POST/PATCH requests, verifying metrics calculations, manual adjustments, audit trace loggers, and confirming locked entries cannot be tampered with.*

---

## 🔒 Compliance Deliverables Included

We have created comprehensive, in-depth reports detailing our post-submission audit criteria:
1.  📂 **[MODEL.md](file:///d:/Breathe%20ESG%20Assignment/MODEL.md)**: Explains the multi-tenant scope isolation, unit standardizer mappings, and daily pro-rating algorithms.
2.  📂 **[DECISIONS.md](file:///d:/Breathe%20ESG%20Assignment/DECISIONS.md)**: Details the resolved ambiguities (utility months, Haversine equations, parsing errors representation) and standard PM escalation questions.
3.  📂 **[TRADEOFFS.md](file:///d:/Breathe%20ESG%20Assignment/TRADEOFFS.md)**: Documents the three deliberate omissions (PDF OCR layers, live dynamic API Tomorrow's ElectricityMap feeds, and SAML SSO auth boilerplate) and long-term production release roadmaps.
4.  📂 **[SOURCES.md](file:///d:/Breathe%20ESG%20Assignment/SOURCES.md)**: Summarizes standard module tables (MSEG/MKPF, PGE ESPI Green Button data structure, Concur Travel expense lines) and potential enterprise failure vectors.
