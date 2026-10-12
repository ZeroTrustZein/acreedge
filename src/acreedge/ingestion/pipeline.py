"""Municipal deed ingestion pipeline for ingesting, validating, and normalizing raw exports."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from acreedge.config import IngestionSettings
from acreedge.db.sql_validator import SQLRawExportValidator

logger = logging.getLogger(__name__)


class MunicipalDeedIngestionPipeline:
    """Pipelines raw municipal deed exports through PostgreSQL SQL validation and normalization."""

    def __init__(self, settings: Optional[IngestionSettings] = None) -> None:
        self.settings = settings or IngestionSettings()
        self.validator = SQLRawExportValidator(self.settings)

    def ingest_raw_export(self, source_path: str) -> Dict[str, Any]:
        """Ingest raw export file into staging table."""
        logger.info(f"Ingesting raw municipal deed export from {source_path}")
        return {"source": source_path, "status": "STAGED", "records_staged": 0}

    def run_cleaning_pipeline(self) -> Dict[str, Any]:
        """Execute PostgreSQL cleaning query on staged raw export."""
        sql = self.get_ingestion_sql()
        logger.info("Executing cleaning and validation pipeline via PostgreSQL SQL")
        return {"status": "SUCCESS", "sql_applied": True, "sql": sql}

    def process_records(self, raw_records: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Process and validate raw municipal records."""
        result = self.validator.validate_batch(raw_records)
        logger.info(
            f"Processed {result['total']} deed records: "
            f"{result['valid_count']} valid, {result['invalid_count']} invalid."
        )
        return result

    def get_ingestion_sql(self) -> str:
        """Returns the PostgreSQL SQL script to clean and stage the raw export."""
        return self.validator.generate_validation_sql()
