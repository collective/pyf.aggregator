"""
npm package indexer for storing npm package metadata in Typesense.

Transforms npm package data and indexes it into the shared packages collection.
"""

import re
from datetime import datetime

from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger


class NpmIndexer(TypesenceConnection, TypesensePackagesCollection):
    """Index npm package data into Typesense."""

    def clean_data(self, data):
        """Clean and normalize npm package data for Typesense.

        Args:
            data: Raw package data dict

        Returns:
            Cleaned data dict ready for indexing
        """
        list_fields = ["requires_dist", "classifiers", "keywords"]

        # Ensure registry is set
        if "registry" not in data:
            data["registry"] = "npm"

        # Parse keywords: handle both list and string formats
        keywords = data.get("keywords")
        if keywords:
            if isinstance(keywords, str):
                # Split by comma and whitespace, strip, filter empty
                data["keywords"] = [
                    k.strip() for k in re.split(r"[,\s]+", keywords) if k.strip()
                ]
            elif isinstance(keywords, list):
                data["keywords"] = [k.strip() for k in keywords if k and k.strip()]

        for key, value in data.items():
            if key in list_fields and value is None:
                data[key] = []
                continue
            if key == "upload_timestamp":
                # Use 0 for missing timestamps (sorts to bottom in desc order)
                if value is None or value == "":
                    data[key] = 0
                continue
            # npm score fields should remain as floats
            if key.startswith("npm_") and key.endswith("_score"):
                if value is None:
                    data[key] = 0.0
                continue
            if value is None:
                data[key] = ""

        return data

    def index_data(self, data, i, target):
        """Batch import data into Typesense.

        Args:
            data: List of package documents
            i: Current count for logging
            target: Target collection name
        """
        logger.info(f"Index {i} packages from npm into collection: {target}")
        res = self.client.collections[target].documents.import_(
            data, {"action": "upsert"}
        )
        # Log any errors
        if isinstance(res, list):
            errors = [r for r in res if not r.get("success", True)]
            if errors:
                for err in errors[:5]:
                    logger.warning(f"Index error: {err}")

    def __call__(self, aggregator, target):
        """Run the indexing process.

        Args:
            aggregator: NpmAggregator instance to iterate over
            target: Target Typesense collection name
        """
        i = 0
        logger.info(f"[{datetime.now()}] Start aggregating packages from npm...")
        batch = []
        bsize = 50

        for identifier, data in aggregator:
            data["id"] = identifier
            data["identifier"] = identifier
            data = self.clean_data(data)
            logger.info(f"Index package: {identifier}")
            batch.append(data)
            i += 1
            if i % bsize == 0:
                self.index_data(batch, i, target)
                batch = []

        if batch:
            self.index_data(batch, i, target)

        logger.info(f"[{datetime.now()}] npm aggregation finished!")
