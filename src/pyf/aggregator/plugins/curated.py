from pathlib import Path

import yaml
import os

_current_dir = Path(os.path.dirname(__file__))

with open(_current_dir / "curated.yaml", 'r') as fio:
    CURATED = yaml.safe_load(fio)

def process_curated(identifier, data):
    curated = CURATED.get(data["name"], None)
    if curated is not None:
        data['curated'] = curated

def load_curated(settings):
    return process_curated
