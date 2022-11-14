from datetime import datetime
from pyf.aggregator.db import TypesenceConnection, TypesensePackagesCollection
from pyf.aggregator.logger import logger


class Indexer(TypesenceConnection, TypesensePackagesCollection):
    def clean_data(self, data):
        list_fields = ["requires_dist", "classifiers"]
        for key, value in data.items():
            if key in list_fields and value == None:
                data[key] = []
                continue
            if value is None:
                data[key] = ""
        return data

    def index_data(self, data, i, target):
        logger.info(f"Aggregated {i} packages from PyPi :)")
        self.client.collections[target].documents.import_(
            data, {"action": "upsert"}
        )

    def __call__(self, aggregator, target):
        i = 0
        logger.info(f"[{datetime.now()}] Start aggregating packages from PyPi...")
        batch = []
        for identifier, data in aggregator:
            data["id"] = identifier
            data = self.clean_data(data)
            logger.info(f"Index package: {identifier}")
            batch.append(data)
            i += 1
            if i % 10 == 0:
                self.index_data(batch, i, target)
                batch = []

        logger.info(f"Aggregated {i} packages from PyPi :)")
        logger.info(f"[{datetime.now()}] Aggregation finished!")
