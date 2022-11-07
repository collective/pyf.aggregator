#!/bin/sh

curl "http://localhost:8108/collections/packages" -X PATCH -H "Content-Type: application/json" -H "X-TYPESENSE-API-KEY: OGBPyJWlzA2dSdt9b8ZxAs8wFOVb0eNG7lSctnzbyBLc8SWR" \
       -d '{
         "fields": [
           {"name": "version_raw", "drop": true},
           {"name": "version_raw", "type": "string", "sort": true, "facet": true}
         ]
       }'

