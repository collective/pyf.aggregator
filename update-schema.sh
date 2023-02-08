#!/bin/sh

curl "http://localhost:8108/collections/packages4" -X PATCH -H "Content-Type: application/json" -H "X-TYPESENSE-API-KEY: UoFZffes6enMtkRQYgcNY6peF6txGwHP" \
       -d '{
         "fields": [
           {"name": "upload_timestamp", "type": "string", "sort": true, "optional": true}
         ]
       }'

