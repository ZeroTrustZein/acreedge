"""Stage 6/10: Comprehensive test suite for SQL-based raw deed export cleaning and validation on PostgreSQL.

Tests PostgreSQL DDL generation, data transformation queries, quarantine isolation,
audit reporting, PostGIS spatial queries, and Python in-memory validation edge cases.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from acreedge.config import IngestionSettings
from acreedge.db.sql_validator import SQLRawExportValidator
from acreedge.types import (
    CleanDeedRecord,
    RawDeedRecord,
    ValidationBatchResult,
    ValidationError,
)


def test_sql_validator_default_ddl():
    """Verify standard PostgreSQL DDL for raw staging, clean, and quarantine tables."""
    validator = SQLRawExportValidator()
    ddl = validator.generate_schema_ddl()

    assert "CREATE TABLE IF NOT EXISTS raw_municipal_deeds" in ddl
    assert "raw_id BIGSERIAL PRIMARY KEY" in ddl
    assert "parcel_id VARCHAR(64)" in ddl
    assert "grantor VARCHAR(255)" in ddl
    assert "grantee VARCHAR(255)" in ddl
    assert "sale_date VARCHAR(64)" in ddl
    assert "sale_price_raw VARCHAR(64)" in ddl
    assert "book_page VARCHAR(64)" in ddl
    assert "recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP" in ddl

    assert "CREATE TABLE IF NOT EXISTS validated_deeds" in ddl
    assert "deed_id BIGSERIAL PRIMARY KEY" in ddl
    assert "parcel_id VARCHAR(64) NOT NULL" in ddl
    assert "sale_date DATE NOT NULL" in ddl
    assert "sale_price NUMERIC(14, 2) NOT NULL" in ddl
    assert "is_arms_length BOOLEAN DEFAULT TRUE" in ddl
    assert "CONSTRAINT chk_sale_price CHECK (sale_price >= 100.0)" in ddl

    assert "CREATE TABLE IF NOT EXISTS quarantined_deeds" in ddl
    assert "quarantine_id BIGSERIAL PRIMARY KEY" in ddl
    assert "raw_id BIGINT" in ddl
    assert "rejection_reason VARCHAR(255)" in ddl
    assert "raw_payload JSONB" in ddl

    assert "CREATE INDEX IF NOT EXISTS idx_validated_deeds_parcel" in ddl
    assert "CREATE INDEX IF NOT EXISTS idx_validated_deeds_date" in ddl
    assert "CREATE INDEX IF NOT EXISTS idx_quarantined_deeds_parcel" in ddl


def test_sql_validator_custom_settings_ddl():
    """Verify DDL respects custom table names and price threshold from IngestionSettings."""
    custom_settings = IngestionSettings(
        raw_export_table="stg_deeds_custom",
        clean_table="dw_deeds_clean",
        quarantine_table="err_deeds_quarantine",
        min_sale_price=5000.0,
    )
    validator = SQLRawExportValidator(settings=custom_settings)
    ddl = validator.generate_schema_ddl()

    assert "CREATE TABLE IF NOT EXISTS stg_deeds_custom" in ddl
    assert "CREATE TABLE IF NOT EXISTS dw_deeds_clean" in ddl
    assert "CREATE TABLE IF NOT EXISTS err_deeds_quarantine" in ddl
    assert "CONSTRAINT chk_sale_price CHECK (sale_price >= 5000.0)" in ddl
    assert "idx_dw_deeds_clean_parcel" in ddl
    assert "idx_err_deeds_quarantine_parcel" in ddl


def test_sql_validator_validation_sql_syntax():
    """Verify PostgreSQL cleaning and type-casting INSERT query syntax."""
    validator = SQLRawExportValidator()
    sql = validator.generate_validation_sql()

    assert "INSERT INTO validated_deeds" in sql
    assert "TRIM(UPPER(raw.parcel_id)) AS parcel_id" in sql
    assert "TRIM(COALESCE(raw.grantor, 'UNKNOWN')) AS grantor" in sql
    assert "TRIM(COALESCE(raw.grantee, 'UNKNOWN')) AS grantee" in sql
    assert "CAST(raw.sale_date AS DATE) AS sale_date" in sql
    assert "REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g')" in sql
    assert "CAST(REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14,2)) AS sale_price" in sql
    assert "COALESCE(TRIM(raw.deed_type), 'DEED') AS deed_type" in sql
    assert "TRIM(raw.book_page) AS book_page" in sql
    assert ">= 100.0" in sql
    assert "TRIM(UPPER(raw.grantor)) <> TRIM(UPPER(raw.grantee))" in sql
    assert "ON CONFLICT DO NOTHING;" in sql


def test_sql_validator_quarantine_sql_reasons():
    """Verify PostgreSQL quarantine query isolates records with exact rejection codes."""
    validator = SQLRawExportValidator()
    sql = validator.generate_quarantine_sql()

    assert "INSERT INTO quarantined_deeds" in sql
    assert "WHEN raw.parcel_id IS NULL OR TRIM(raw.parcel_id) = '' THEN 'MISSING_PARCEL_ID'" in sql
    assert "WHEN raw.sale_date IS NULL OR TRIM(raw.sale_date) = '' THEN 'MISSING_SALE_DATE'" in sql
    assert "WHEN raw.sale_price_raw IS NULL OR TRIM(raw.sale_price_raw) = '' THEN 'MISSING_SALE_PRICE'" in sql
    assert "THEN 'INVALID_PRICE_FORMAT'" in sql
    assert "THEN 'PRICE_BELOW_MINIMUM'" in sql
    assert "WHEN TRIM(UPPER(raw.grantor)) = TRIM(UPPER(raw.grantee)) THEN 'NON_ARMS_LENGTH_TRANSFER'" in sql
    assert "ELSE 'VALIDATION_FAILED'" in sql
    assert "TO_JSONB(raw) AS raw_payload" in sql


def test_sql_validator_audit_and_pipeline():
    """Verify PostgreSQL audit calculation and transactional pipeline script."""
    validator = SQLRawExportValidator()
    audit_sql = validator.generate_audit_sql()
    pipeline_sql = validator.build_pipeline_sql()

    assert "total_raw" in audit_sql
    assert "total_validated" in audit_sql
    assert "total_quarantined" in audit_sql
    assert "pass_rate" in audit_sql
    assert "NULLIF(" in audit_sql

    assert pipeline_sql.startswith("BEGIN;")
    assert "INSERT INTO validated_deeds" in pipeline_sql
    assert "INSERT INTO quarantined_deeds" in pipeline_sql
    assert pipeline_sql.endswith("COMMIT;\n")


def test_sql_validator_spatial_comps():
    """Verify PostGIS geography spatial search query generation."""
    validator = SQLRawExportValidator()
    spatial_sql = validator.generate_spatial_comps_sql(
        latitude=30.2672, longitude=-97.7431, radius_miles=10.0
    )

    assert "ST_SetSRID(ST_MakePoint(-97.7431, 30.2672), 4326)::geography" in spatial_sql
    assert "16093.44" in spatial_sql
    assert "ST_DWithin(geom," in spatial_sql
    assert "is_arms_length = TRUE" in spatial_sql
    assert "ORDER BY distance_miles ASC;" in spatial_sql


def test_clean_record_valid_arms_length():
    """Verify in-memory cleaning of normal arms-length deed."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": " 100-204-55A ",
        "grantor": "Apex Realty Corp",
        "grantee": "Summit Buyer LLC",
        "sale_date": "2026-04-01",
        "sale_price_raw": "$1,750,000.00",
        "deed_type": "WARRANTY DEED",
        "book_page": "B104-P50",
    }
    clean = validator.clean_record(rec)
    assert clean is not None
    assert clean["parcel_id"] == "100-204-55A"
    assert clean["grantor"] == "Apex Realty Corp"
    assert clean["grantee"] == "Summit Buyer LLC"
    assert clean["sale_date"] == "2026-04-01"
    assert clean["sale_price"] == 1750000.0
    assert clean["deed_type"] == "WARRANTY DEED"
    assert clean["book_page"] == "B104-P50"
    assert clean["is_arms_length"] is True


def test_clean_record_missing_parcel_id():
    """Verify record without parcel_id is rejected."""
    validator = SQLRawExportValidator()
    assert validator.clean_record({"parcel_id": "", "sale_price_raw": "50000"}) is None
    assert validator.clean_record({"parcel_id": "   ", "sale_price_raw": "50000"}) is None
    assert validator.clean_record({"sale_price_raw": "50000"}) is None


def test_clean_record_missing_sale_date():
    """Verify record without sale_date is rejected (covers line 216)."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": "100-204-55A",
        "grantor": "A",
        "grantee": "B",
        "sale_price_raw": "500000",
        "sale_date": "",
    }
    assert validator.clean_record(rec) is None

    rec_whitespace = dict(rec, sale_date="   ")
    assert validator.clean_record(rec_whitespace) is None


def test_clean_record_invalid_price_format():
    """Verify record with malformed price strings that cause ValueError (covers line 205-206)."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": "100-204-55A",
        "grantor": "A",
        "grantee": "B",
        "sale_date": "2026-01-01",
        "sale_price_raw": "1.2.3.4",
    }
    assert validator.clean_record(rec) is None

    rec_dots = dict(rec, sale_price_raw="...")
    assert validator.clean_record(rec_dots) is None


def test_clean_record_below_minimum_price():
    """Verify record with nominal transfer price below threshold is rejected."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": "100-204-55A",
        "grantor": "Parent LLC",
        "grantee": "Child LLC",
        "sale_date": "2026-01-01",
        "sale_price_raw": "$10.00",
    }
    assert validator.clean_record(rec) is None


def test_clean_record_non_arms_length_related_parties():
    """Verify record where grantor matches grantee is preserved as non-arms-length."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": "100-204-55A",
        "grantor": "Apex Properties LLC",
        "grantee": "apex properties llc",
        "sale_date": "2026-01-01",
        "sale_price_raw": "$1,200,000.00",
    }
    clean = validator.clean_record(rec)
    assert clean is not None
    assert clean["is_arms_length"] is False


def test_clean_record_unknown_grantor():
    """Verify record where grantor is UNKNOWN is marked not arms length."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": "100-204-55A",
        "grantee": "Buyer LLC",
        "sale_date": "2026-01-01",
        "sale_price_raw": "$500,000.00",
    }
    clean = validator.clean_record(rec)
    assert clean is not None
    assert clean["grantor"] == "UNKNOWN"
    assert clean["is_arms_length"] is False


def test_clean_to_model_invalid_date_exception():
    """Verify clean_to_model handles Pydantic model construction exception (covers line 245-246)."""
    validator = SQLRawExportValidator()
    rec = {
        "parcel_id": "100-204-55A",
        "grantor": "Seller LLC",
        "grantee": "Buyer LLC",
        "sale_date": "invalid-non-iso-date-9999",
        "sale_price_raw": "$500,000.00",
    }
    res = validator.clean_to_model(rec)
    assert res is None


def test_clean_to_model_with_raw_deed_record():
    """Verify clean_to_model works seamlessly with RawDeedRecord instance."""
    validator = SQLRawExportValidator()
    raw = RawDeedRecord(
        parcel_id="100-204-55A",
        grantor="Seller LLC",
        grantee="Buyer LLC",
        sale_date="2026-03-20",
        sale_price_raw="$2,500,000.00",
    )
    clean = validator.clean_to_model(raw)
    assert clean is not None
    assert isinstance(clean, CleanDeedRecord)
    assert clean.parcel_id == "100-204-55A"
    assert clean.sale_price == 2500000.0


def test_validate_batch_models_mixed_batch():
    """Verify validate_batch_models separates valid models from structured errors."""
    validator = SQLRawExportValidator()
    batch = [
        RawDeedRecord(
            parcel_id="PARCEL-1",
            grantor="Seller 1",
            grantee="Buyer 1",
            sale_date="2026-01-10",
            sale_price_raw="$500,000.00",
        ),
        {
            "parcel_id": "",
            "grantor": "Seller 2",
            "grantee": "Buyer 2",
            "sale_date": "2026-01-10",
            "sale_price_raw": "$600,000.00",
        },
        RawDeedRecord(
            parcel_id="PARCEL-3",
            grantor="Seller 3",
            grantee="Buyer 3",
            sale_date="2026-01-10",
            sale_price_raw="$5.00",  # Below threshold
        ),
    ]
    result: ValidationBatchResult = validator.validate_batch_models(batch)
    assert result.total_records == 3
    assert result.valid_records == 1
    assert result.rejected_records == 2
    assert round(result.pass_rate, 2) == 0.33
    assert len(result.cleaned_records) == 1
    assert len(result.errors) == 2
    assert result.errors[0].record_index == 1
    assert result.errors[1].record_index == 2
    assert result.errors[1].parcel_id == "PARCEL-3"


def test_validate_batch_dictionary_method():
    """Verify validate_batch returns dictionary format with valid and invalid records."""
    validator = SQLRawExportValidator()
    raws = [
        {
            "parcel_id": "100-204-55A",
            "grantor": "Seller",
            "grantee": "Buyer",
            "sale_date": "2026-02-15",
            "sale_price_raw": "1000000",
        },
        {"parcel_id": "", "sale_price_raw": "500"},
    ]
    res = validator.validate_batch(raws)
    assert res["total"] == 2
    assert res["valid_count"] == 1
    assert res["invalid_count"] == 1
    assert len(res["valid_records"]) == 1
    assert len(res["invalid_records"]) == 1
