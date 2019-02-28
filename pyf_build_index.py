import os
from elasticsearch import Elasticsearch

client = Elasticsearch([
    {'host': 'localhost', 'port': '9200'}
])

for filename in os.listdir('data'):
    with open('data/' + filename) as file_obj:
        index_keywords = {
            'index': 'packages',
            'doc_type': 'content',
            'id': filename.replace('.json', ''),
            'body': file_obj.read()
        }
        client.index(**index_keywords)
