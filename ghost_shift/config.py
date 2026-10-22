import os
import yaml
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("config.yaml")

def load_config(path=DEFAULT_CONFIG_PATH):
    if not path.exists():
        return {}
    with open(path, "r") as f:
        return yaml.safe_load(f)
