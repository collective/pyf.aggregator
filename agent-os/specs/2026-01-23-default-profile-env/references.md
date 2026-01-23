# References

## Pattern Reference: queue.py

The `queue.py` module demonstrates the established pattern for loading environment variables:

```python
from dotenv import load_dotenv
import os

load_dotenv()

COLLECTION_NAME = os.getenv("TYPESENSE_COLLECTION", "plone")
```

This pattern is followed for consistency across the codebase.
