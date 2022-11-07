# from elasticsearch import Elasticsearch
# from elasticsearch_dsl import Mapping
from pyf.aggregator.logger import logger
from pyf.aggregator.db import TypesenceBase
from datetime import datetime
import typesense



class Indexer(TypesenceBase):

    def clean_data(self, data):
        list_fields = ["requires_dist", "classifiers"]
        for key, value in data.items():
            if key in list_fields and value == None:
                data[key] = []
                continue
            if value is None:
                data[key] = ""
        return data

    def index_data(self, data, i):
        logger.info(f"Aggregated {i} packages from PyPi :)")
        self.client.collections[self.collection_name].documents.import_(
            data, {"action": "upsert"}
        )

    def __call__(self, aggregator):
        i = 0
        logger.info(f"[{datetime.now()}] Start aggregating packages from PyPi...")
        batch = []
        for identifier, data in aggregator:
            data["id"] = identifier
            data = self.clean_data(data)
            logger.info(f"Index package: {identifier}")
            batch.append(data)
            i += 1
            if i % 100 == 0:
                self.index_data(batch, i)
                batch = []

        logger.info(f"Aggregated {i} packages from PyPi :)")
        logger.info(f"[{datetime.now()}] Aggregation finished!")
