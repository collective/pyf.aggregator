import os
from elasticsearch import Elasticsearch
from elasticsearch_dsl import Mapping
from config import PACKAGE_FIELD_MAPPING

client = Elasticsearch([{"host": "localhost", "port": "9200"}])


def set_mapping(mapping_name, field_mapping):
    mapping = Mapping(mapping_name)
    for field_id, field_type in field_mapping.iteritems():
        mapping.field(field_id, field_type)
    mapping.save(index="packages", using=client)


def set_package_index():
    for filename in os.listdir("data"):
        with open("data/" + filename) as file_obj:
            index_keywords = {
                "index": "packages",
                "doc_type": "package",
                "id": filename[:-5],
                "body": file_obj.read(),
            }
            client.index(**index_keywords)


set_mapping('package', PACKAGE_FIELD_MAPPING)
set_package_index()
