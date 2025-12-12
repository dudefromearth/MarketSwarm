# services/mmaker/intel/tile_hash.py

import hashlib
import json
from typing import Dict, Any

def compute_tile_hash(tile: Dict[str, Any]) -> str:
    """
    Stable hash of the minimal tile fields.
    A change in pricing or timestamps must change the hash.
    """
    relevant = {
        "legs": tile["legs"],
        "last": tile["last"],
        "built": tile["built"],
    }
    s = json.dumps(relevant, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]