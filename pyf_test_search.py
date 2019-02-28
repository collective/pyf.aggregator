from elasticsearch import Elasticsearch
from elasticsearch_dsl import Search


client = Elasticsearch([
    {'host': 'localhost', 'port': '9200'}
])

search_obj = Search(using=client, index='packages')

search_obj = search_obj.filter(
    'terms',
    classifiers=['Framework :: Plone :: 4.2']
)

result = search_obj.execute()
print result
