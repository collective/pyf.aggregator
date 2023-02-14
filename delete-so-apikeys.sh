#!/bin/bash

echo "delete key:" $1
curl 'http://localhost:8108/keys/'$1 \
    -X DELETE \
    -H "X-TYPESENSE-API-KEY: OGBPyJWlzA2dSdt9b8ZxAs8wFOVb0eNG7lSctnzbyBLc8SWR" \


