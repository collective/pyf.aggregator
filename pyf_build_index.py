from elasticsearch import Elasticsearch
from elasticsearch_dsl import Boolean
from elasticsearch_dsl import Date
from elasticsearch_dsl import Integer
from elasticsearch_dsl import Keyword
from elasticsearch_dsl import Mapping
from elasticsearch_dsl import Nested
from elasticsearch_dsl import Text

import os


client = Elasticsearch([{"host": "localhost", "port": "9200"}])

mapping = Mapping("package")
mapping.field("author", Text())
mapping.field("author_email", Text())
mapping.field("bugtrack_url", Text())
mapping.field("classifiers", Keyword())
mapping.field("description", Text())
mapping.field("description_content_type", Text())
mapping.field("docs_url", Text())
mapping.field("download_url", Text())
mapping.field("home_page", Text())
mapping.field("keywords", Text())
mapping.field("license", Text())
mapping.field("maintainer", Text())
mapping.field("maintainer_email", Text())
mapping.field("name", Text())
mapping.field("package_url", Text())
mapping.field("platform", Text())
mapping.field("project_url", Text())
mapping.field("project_urls", Nested(dynamic=True))
mapping.field("release_url", Text())
mapping.field("requires_dist", Text())
mapping.field("requires_python", Text())
mapping.field("summary", Text())
mapping.field("version", Text())
mapping.field(
    "urls",
    Nested(
        properties={
            "comment_text": Text(),
            "digests": Nested(properties={"md5": Text(), "sha256": Text()}),
            "filename": Text(),
            "has_sig": Boolean(),
            "packagetype": Text(),
            "python_version": Text(),
            "requires_python": Text(),
            "size": Integer(),
            "upload_time": Date(),
            "url": Text()
        }
    ),
)
mapping.save(index="packages", using=client)

for filename in os.listdir("data"):
    with open("data/" + filename) as file_obj:
        index_keywords = {
            "index": "packages",
            "doc_type": "package",
            "id": filename[:-5],
            "body": file_obj.read(),
        }
        client.index(**index_keywords)
