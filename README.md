# AcreEdge

> Autonomous Multi-Agent Underwriting Engine, Valuation MCP Server, and Municipal Deed Ingestion Pipeline with Hybrid pgvector/Graph-RAG.

AcreEdge automates municipal real estate deed ingestion, PostgreSQL raw export data cleansing, spatial comparative market analysis, autonomous multi-agent underwriting due diligence, and tool exposure via Model Context Protocol (MCP).

---

## Key Features

- **SQL Raw Export Cleaner & Validator (PostgreSQL)**:
  - Generates DDL for staging (`raw_deed_exports`), clean (`clean_deeds`), and quarantine (`quarantined_deeds`) tables.
  - Sanitizes messy currency strings (`$4,250,000.00` -> `4250000.00`) via SQL `REGEXP_REPLACE`.
  - Flags non-arms-length conveyances (quitclaim deeds, sheriff sales, transfers where grantor equals grantee, sub-minimum prices).
  - Spatial comparative deed search with PostGIS (`ST_DWithin`, `ST_MakePoint`).
  - Batch in-memory or in-database validation with structured quarantine error tracking.
- **Municipal Deed Ingestion Pipeline**:
  - Validates and routes deed batches from municipal county records.
  - Auto-quarantines corrupted, unrecorded, or below-threshold records.
- **Autonomous Multi-Agent Underwriting Swarm**:
  - Parallel audit across 6 specialized roles: Title, Zoning, Environmental, Financial, Structural, and Market.
  - Synthesizes risk scores and audit findings into an `UnderwritingReport` (`APPROVED` vs `FLAGGED`).
- **Valuation Engine**:
  - Direct sales comparison, capitalization rate (NOI / cap rate), and price per square foot calculations.
- **Hybrid pgvector & Graph-RAG**:
  - Dense semantic retrieval via pgvector embeddings combined with topological entity traversal.
- **Model Context Protocol (MCP) Server**:
  - Exposes `deed_lookup`, `underwrite_parcel`, `valuation_comps`, and `hybrid_rag_query` as MCP tools over JSON-RPC.

---

## Architecture Overview

```
                      Raw Municipal Deed Exports (CSV / JSON)
                                      │
                                      ▼
             ┌─────────────────────────────────────────────────┐
             │      SQLRawExportValidator / PostgreSQL         │
             │   - DDL Staging (raw_deed_exports)              │
             │   - Cleaning & Sanitization (Regex, Casts)      │
             │   - Arm's-Length Detection                      │
             │   - Quarantine Routing                          │
             └───────────────┬─────────────────┬───────────────┘
                             │                 │
                (Invalid)    ▼                 ▼   (Valid)
                 quarantined_deeds        clean_deeds
                                               │
                                               ▼
             ┌─────────────────────────────────────────────────┐
             │           Hybrid pgvector / Graph-RAG           │
             │         - Dense Document Embeddings             │
             │         - Property & Deed Knowledge Graph       │
             └───────────────────────┬─────────────────────────┘
                                     │
                                     ▼
             ┌─────────────────────────────────────────────────┐
             │           SwarmOrchestrator (Agents)            │
             │  Title | Zoning | Environmental | Financial ... │
             └───────────────────────┬─────────────────────────┘
                                     │
                         ┌───────────┴───────────┐
                         ▼                       ▼
                  CLI Interface             MCP Server
             (acreedge underwrite ...)   (Model Context Protocol)
```

---

## Installation

### Requirements
- Python >= 3.10
- PostgreSQL >= 14 with `pgvector` and `postgis` extensions

### Setup

```bash
# Clone repository
git clone https://github.com/ZeroTrustZein/acreedge.git
cd acreedge

# Install package and dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"
```

---

## Configuration

Settings are managed via environment variables or a `.env` file (`AcreEdgeSettings`):

```bash
cp .env.example .env
```

| Variable | Default | Description |
|---|---|---|
| `ACREEDGE_ENV` | `development` | Runtime environment (`development`, `staging`, `production`) |
| `ACREEDGE_DEBUG` | `false` | Enable verbose diagnostic logging |
| `ACREEDGE_DB__HOST` | `localhost` | PostgreSQL host |
| `ACREEDGE_DB__PORT` | `5432` | PostgreSQL port |
| `ACREEDGE_DB__USER` | `postgres` | PostgreSQL username |
| `ACREEDGE_DB__PASSWORD` | `postgres` | PostgreSQL password |
| `ACREEDGE_DB__NAME` | `acreedge_db` | PostgreSQL database name |
| `ACREEDGE_INGESTION__RAW_EXPORT_TABLE` | `raw_deed_exports` | Staging table for raw exports |
| `ACREEDGE_INGESTION__CLEAN_TABLE` | `clean_deeds` | Validated arms-length deeds table |
| `ACREEDGE_INGESTION__QUARANTINE_TABLE` | `quarantined_deeds` | Quarantined invalid records table |
| `ACREEDGE_INGESTION__MIN_SALE_PRICE` | `1000.0` | Minimum dollar threshold for valid transfer |
| `ACREEDGE_MCP__HOST` | `127.0.0.1` | MCP server bind address |
| `ACREEDGE_MCP__PORT` | `8440` | MCP server port |

---

## PostgreSQL Raw Export Cleaning & Validation

The validator (`SQLRawExportValidator`) produces executable SQL statements tailored for PostgreSQL:

### 1. Schema DDL
```sql
CREATE TABLE IF NOT EXISTS raw_deed_exports (
    raw_id BIGSERIAL PRIMARY KEY,
    parcel_id VARCHAR(64),
    grantor VARCHAR(255),
    grantee VARCHAR(255),
    sale_date VARCHAR(64),
    sale_price_raw VARCHAR(64),
    deed_type VARCHAR(64),
    book_page VARCHAR(64),
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clean_deeds (
    deed_id BIGSERIAL PRIMARY KEY,
    parcel_id VARCHAR(64) NOT NULL,
    grantor VARCHAR(255) NOT NULL,
    grantee VARCHAR(255) NOT NULL,
    sale_date DATE NOT NULL,
    sale_price NUMERIC(14, 2) NOT NULL,
    deed_type VARCHAR(64) DEFAULT 'DEED',
    book_page VARCHAR(64),
    is_arms_length BOOLEAN DEFAULT TRUE,
    validated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_sale_price CHECK (sale_price >= 1000.0)
);

CREATE TABLE IF NOT EXISTS quarantined_deeds (
    quarantine_id BIGSERIAL PRIMARY KEY,
    raw_id BIGINT,
    parcel_id VARCHAR(64),
    grantor VARCHAR(255),
    grantee VARCHAR(255),
    rejection_reason VARCHAR(255),
    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Validation & Cleaning Transformation
```sql
INSERT INTO clean_deeds (parcel_id, grantor, grantee, sale_date, sale_price, deed_type, book_page, is_arms_length)
SELECT
    TRIM(r.parcel_id) AS parcel_id,
    UPPER(TRIM(r.grantor)) AS grantor,
    UPPER(TRIM(r.grantee)) AS grantee,
    TO_DATE(r.sale_date, 'YYYY-MM-DD') AS sale_date,
    CAST(REGEXP_REPLACE(r.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14, 2)) AS sale_price,
    COALESCE(NULLIF(UPPER(TRIM(r.deed_type)), ''), 'DEED') AS deed_type,
    NULLIF(TRIM(r.book_page), '') AS book_page,
    TRUE AS is_arms_length
FROM raw_deed_exports r
WHERE
    r.parcel_id IS NOT NULL AND TRIM(r.parcel_id) <> ''
    AND r.grantor IS NOT NULL AND TRIM(r.grantor) <> ''
    AND r.grantee IS NOT NULL AND TRIM(r.grantee) <> ''
    AND UPPER(TRIM(r.grantor)) <> UPPER(TRIM(r.grantee))
    AND UPPER(TRIM(r.deed_type)) NOT IN ('QUITCLAIM', 'SHERIFF', 'TAX DEED', 'GIFT DEED', 'EASEMENT')
    AND CAST(REGEXP_REPLACE(r.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14, 2)) >= 1000.0;
```

---

## CLI Usage

AcreEdge provides a command line interface via `acreedge`:

```bash
# View general info and loaded configuration
acreedge info
acreedge validate-config

# Generate SQL migration and validation scripts
acreedge generate-sql --kind ddl
acreedge generate-sql --kind validation
acreedge generate-sql --kind quarantine
acreedge generate-sql --kind comps --lat 34.0522 --lon -118.2437 --radius 5.0

# Clean raw deed export file or built-in sample
acreedge clean-export
acreedge clean-export --file deeds.json --json-output

# Process ingestion batch
acreedge ingest --dry-run
acreedge ingest --file deeds.json

# Run commercial property valuation
acreedge valuation --property-value 5000000 --square-feet 25000 --cap-rate 0.065

# Perform multi-agent underwriting due diligence
acreedge underwrite 100-204-55A
acreedge underwrite 100-204-55A --json-output

# Query Hybrid RAG knowledge base
acreedge rag-search "commercial conveyances 100 Main St"

# Initialize PostgreSQL schema & extensions
acreedge db-init

# Start or inspect Model Context Protocol server
acreedge serve-mcp --dry-run
acreedge serve-mcp
```

---

## Python API Usage

```python
from acreedge.db.sql_validator import SQLRawExportValidator
from acreedge.agents.orchestrator import SwarmOrchestrator
from acreedge.valuation.engine import ValuationEngine

# 1. Clean and validate raw exports
validator = SQLRawExportValidator()
batch = [
    {
        "parcel_id": "100-204-55A",
        "grantor": "Apex Holdings LLC",
        "grantee": "Meridian Realty Partners",
        "sale_date": "2026-03-15",
        "sale_price_raw": "$4,250,000.00",
        "deed_type": "WARRANTY DEED",
    },
    {
        "parcel_id": "100-204-55B",
        "grantor": "Family Trust",
        "grantee": "Family Trust",
        "sale_date": "2026-04-01",
        "sale_price_raw": "$10.00",
        "deed_type": "QUITCLAIM",
    },
]
result = validator.validate_batch(batch)
print(f"Valid: {result['valid_count']}, Quarantined: {result['invalid_count']}")

# 2. Run multi-agent underwriting due diligence
orchestrator = SwarmOrchestrator()
report = orchestrator.run_due_diligence(parcel_id="100-204-55A")
print(f"Status: {report['overall_status']}, Score: {report['composite_risk_score']}")

# 3. Calculate property valuation
engine = ValuationEngine()
valuation = engine.evaluate(property_value=4250000.0, square_feet=20000, cap_rate=0.06)
print(f"Cap Rate Value: {valuation['cap_rate_value']}, $/sqft: {valuation['value_per_sqft']}")
```

---

## Testing & Quality Assurance

Run test suite, linter, and type checker:

```bash
# Unit and integration tests
python -m pytest

# Coverage report
python -m pytest --cov=acreedge --cov-report=term-missing

# Linting and formatting
python -m ruff check .
python -m ruff format --check .

# Type checking
python -m mypy src
```

---

## License

MIT License. Copyright (c) 2026 Zein.
