from .curated import load_curated

def register_plugins(PLUGINS):
    PLUGINS.append(load_curated)
