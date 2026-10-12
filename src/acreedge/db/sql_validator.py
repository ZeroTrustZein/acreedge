"""SQL queries and validation engine for cleaning raw municipal deed exports on PostgreSQL."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Union

from acreedge.config import IngestionSettings
from acreedge.types import (
    CleanDeedRecord,
    RawDeedRecord,
    ValidationBatchResult,
    ValidationError,
)


class SQLRawExportValidator:
    """Generates PostgreSQL statements to clean and validate municipal deed exports."""

    def __init__(self, settings: Optional[IngestionSettings] = None) -> None:
        self.settings = settings or IngestionSettings()

    def generate_schema_ddl(self) -> str:
        """DDL for raw staging and clean validated tables in PostgreSQL."""
        return f"""
CREATE TABLE IF NOT EXISTS {self.settings.raw_export_table} (
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

CREATE TABLE IF NOT EXISTS {self.settings.clean_table} (
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
    CONSTRAINT chk_sale_price CHECK (sale_price >= {self.settings.min_sale_price})
);

CREATE INDEX IF NOT EXISTS idx_{self.settings.clean_table}_parcel
    ON {self.settings.clean_table}(parcel_id);
CREATE INDEX IF NOT EXISTS idx_{self.settings.clean_table}_date
    ON {self.settings.clean_table}(sale_date);

CREATE TABLE IF NOT EXISTS {self.settings.quarantine_table} (
    quarantine_id BIGSERIAL PRIMARY KEY,
    raw_id BIGINT,
    parcel_id VARCHAR(64),
    rejection_reason VARCHAR(255),
    raw_payload JSONB,
    quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_{self.settings.quarantine_table}_parcel
    ON {self.settings.quarantine_table}(parcel_id);
"""

    def generate_validation_sql(self) -> str:
        """PostgreSQL query to clean, cast, and validate raw staging records into clean table."""
        return f"""
INSERT INTO {self.settings.clean_table} (
    parcel_id,
    grantor,
    grantee,
    sale_date,
    sale_price,
    deed_type,
    book_page,
    is_arms_length
)
SELECT
    TRIM(UPPER(raw.parcel_id)) AS parcel_id,
    TRIM(COALESCE(raw.grantor, 'UNKNOWN')) AS grantor,
    TRIM(COALESCE(raw.grantee, 'UNKNOWN')) AS grantee,
    CAST(raw.sale_date AS DATE) AS sale_date,
    CAST(REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14,2)) AS sale_price,
    COALESCE(TRIM(raw.deed_type), 'DEED') AS deed_type,
    TRIM(raw.book_page) AS book_page,
    CASE
        WHEN CAST(
            REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14,2)
        ) >= {self.settings.min_sale_price}
             AND TRIM(UPPER(raw.grantor)) <> TRIM(UPPER(raw.grantee))
        THEN TRUE
        ELSE FALSE
    END AS is_arms_length
FROM {self.settings.raw_export_table} raw
WHERE
    raw.parcel_id IS NOT NULL
    AND TRIM(raw.parcel_id) <> ''
    AND raw.sale_date IS NOT NULL
    AND raw.sale_price_raw IS NOT NULL
    AND REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') ~ '^[0-9]+(\\.[0-9]+)?$'
    AND CAST(
        REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14,2)
    ) >= {self.settings.min_sale_price}
ON CONFLICT DO NOTHING;
"""

    def generate_quarantine_sql(self) -> str:
        """PostgreSQL query to isolate and log invalid raw export records."""
        return f"""
INSERT INTO {self.settings.quarantine_table} (
    raw_id,
    parcel_id,
    rejection_reason,
    raw_payload
)
SELECT
    raw.raw_id,
    raw.parcel_id,
    CASE
        WHEN raw.parcel_id IS NULL OR TRIM(raw.parcel_id) = '' THEN 'MISSING_PARCEL_ID'
        WHEN raw.sale_date IS NULL OR TRIM(raw.sale_date) = '' THEN 'MISSING_SALE_DATE'
        WHEN raw.sale_price_raw IS NULL OR TRIM(raw.sale_price_raw) = '' THEN 'MISSING_SALE_PRICE'
        WHEN REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g')
             !~ '^[0-9]+(\\.[0-9]+)?$' THEN 'INVALID_PRICE_FORMAT'
        WHEN CAST(
            REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14,2)
        ) < {self.settings.min_sale_price} THEN 'PRICE_BELOW_MINIMUM'
        WHEN TRIM(UPPER(raw.grantor)) = TRIM(UPPER(raw.grantee)) THEN 'NON_ARMS_LENGTH_TRANSFER'
        ELSE 'VALIDATION_FAILED'
    END AS rejection_reason,
    TO_JSONB(raw) AS raw_payload
FROM {self.settings.raw_export_table} raw
WHERE
    raw.parcel_id IS NULL
    OR TRIM(raw.parcel_id) = ''
    OR raw.sale_date IS NULL
    OR raw.sale_price_raw IS NULL
    OR REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') !~ '^[0-9]+(\\.[0-9]+)?$'
    OR CAST(
        REGEXP_REPLACE(raw.sale_price_raw, '[^0-9.]', '', 'g') AS NUMERIC(14,2)
    ) < {self.settings.min_sale_price}
    OR TRIM(UPPER(raw.grantor)) = TRIM(UPPER(raw.grantee));
"""

    def generate_audit_sql(self) -> str:
        """PostgreSQL query computing batch cleaning audit metrics."""
        return f"""
SELECT
    (SELECT COUNT(*) FROM {self.settings.raw_export_table}) AS total_raw,
    (SELECT COUNT(*) FROM {self.settings.clean_table}) AS total_validated,
    (SELECT COUNT(*) FROM {self.settings.quarantine_table}) AS total_quarantined,
    ROUND(
        (SELECT COUNT(*)::NUMERIC FROM {self.settings.clean_table}) /
        NULLIF((SELECT COUNT(*)::NUMERIC FROM {self.settings.raw_export_table}), 0),
        4
    ) AS pass_rate;
"""

    def build_pipeline_sql(self) -> str:
        """Assemble full transactional cleaning and quarantine workflow in PostgreSQL."""
        return (
            "BEGIN;\n"
            f"{self.generate_validation_sql().strip()}\n"
            f"{self.generate_quarantine_sql().strip()}\n"
            "COMMIT;\n"
        )

    def generate_spatial_comps_sql(
        self, latitude: float, longitude: float, radius_miles: float = 5.0
    ) -> str:
        """PostGIS spatial query to retrieve comparable arms-length deeds within radius."""
        radius_meters = radius_miles * 1609.344
        pt = f"ST_SetSRID(ST_MakePoint({longitude}, {latitude}), 4326)::geography"
        return f"""
SELECT
    deed_id,
    parcel_id,
    grantor,
    grantee,
    sale_date,
    sale_price,
    deed_type,
    is_arms_length,
    ROUND((ST_Distance(geom, {pt}) / 1609.344)::numeric, 2) AS distance_miles
FROM {self.settings.clean_table}
WHERE ST_DWithin(geom, {pt}, {radius_meters})
  AND is_arms_length = TRUE
ORDER BY distance_miles ASC;
"""

    def clean_record(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """In-memory cleaning and validation for a single raw export record."""
        parcel_id = str(record.get("parcel_id", "")).strip().upper()
        if not parcel_id:
            return None

        price_raw = str(record.get("sale_price_raw", record.get("sale_price", "0")))
        clean_price_str = re.sub(r"[^0-9.]", "", price_raw)
        try:
            sale_price = float(clean_price_str) if clean_price_str else 0.0
        except ValueError:
            return None

        if sale_price < self.settings.min_sale_price:
            return None

        grantor = str(record.get("grantor", "UNKNOWN")).strip()
        grantee = str(record.get("grantee", "UNKNOWN")).strip()
        sale_date = str(record.get("sale_date", "")).strip()

        if not sale_date:
            return None

        is_arms_length = (
            sale_price >= self.settings.min_sale_price
            and grantor.upper() != grantee.upper()
            and grantor != "UNKNOWN"
        )

        return {
            "parcel_id": parcel_id,
            "grantor": grantor,
            "grantee": grantee,
            "sale_date": sale_date,
            "sale_price": sale_price,
            "deed_type": str(record.get("deed_type", "DEED")).strip(),
            "book_page": str(record.get("book_page", "")).strip(),
            "is_arms_length": is_arms_length,
        }

    def clean_to_model(
        self, record: Union[Dict[str, Any], RawDeedRecord]
    ) -> Optional[CleanDeedRecord]:
        """Convert and validate raw input into a strongly typed CleanDeedRecord."""
        raw_dict = record.model_dump() if isinstance(record, RawDeedRecord) else record
        cleaned = self.clean_record(raw_dict)
        if cleaned is None:
            return None
        try:
            return CleanDeedRecord(**cleaned)
        except Exception:
            return None

    def validate_batch_models(
        self, records: List[Union[Dict[str, Any], RawDeedRecord]]
    ) -> ValidationBatchResult:
        """Validate batch returning structured ValidationBatchResult schema."""
        valid_models: List[CleanDeedRecord] = []
        errors: List[ValidationError] = []

        for idx, rec in enumerate(records):
            raw_dict = rec.model_dump() if isinstance(rec, RawDeedRecord) else rec
            cleaned = self.clean_to_model(raw_dict)
            if cleaned is not None:
                valid_models.append(cleaned)
            else:
                p_id = str(raw_dict.get("parcel_id", ""))
                errors.append(
                    ValidationError(
                        record_index=idx,
                        parcel_id=p_id or None,
                        field="record",
                        message="Failed validation criteria or minimum sale price threshold",
                        raw_value=raw_dict,
                    )
                )

        total = len(records)
        valid_count = len(valid_models)
        rejected_count = len(errors)
        pass_rate = round(valid_count / total, 4) if total > 0 else 0.0

        return ValidationBatchResult(
            total_records=total,
            valid_records=valid_count,
            rejected_records=rejected_count,
            pass_rate=pass_rate,
            errors=errors,
            cleaned_records=valid_models,
        )

    def validate_batch(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate and clean an in-memory batch of raw deed records."""
        valid: List[Dict[str, Any]] = []
        invalid: List[Dict[str, Any]] = []

        for rec in records:
            cleaned = self.clean_record(rec)
            if cleaned is not None:
                valid.append(cleaned)
            else:
                invalid.append(rec)

        return {
            "total": len(records),
            "valid_count": len(valid),
            "invalid_count": len(invalid),
            "valid_records": valid,
            "invalid_records": invalid,
        }
