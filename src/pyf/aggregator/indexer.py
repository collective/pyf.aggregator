from elasticsearch import Elasticsearch
from elasticsearch_dsl import Mapping
from pyf.aggregator.config import PACKAGE_FIELD_MAPPING


class Indexer(object):
    def __init__(self):
        self.client = Elasticsearch([{"host": "localhost", "port": "9200"}])
        self.set_mapping("package", PACKAGE_FIELD_MAPPING)

    def set_mapping(self, mapping_name, field_mapping):
        mapping = Mapping(mapping_name)
        for field_id in field_mapping:
            mapping.field(field_id, field_mapping[field_id])
        mapping.save(index="packages", using=self.client)

    def __call__(self, aggregator):
        for identifier, data in aggregator:
            index_keywords = {
                "index": "packages",
                "doc_type": "package",
                "id": identifier,
                "body": data,
            }
            self.client.index(**index_keywords)
