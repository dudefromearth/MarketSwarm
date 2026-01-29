# Recommendation: Create Schemas

**Highly useful — essential for production stability.**

Reasons:
- UI (React) needs predictable structure for grid rendering, popups, diffs.
- Prevents builder/UI drift.
- Enables validation (e.g., pydantic/jsonschema).
- Supports incremental diffs (only changed tiles).
- Allows versioning for future changes (e.g., add metadata).

**Proposed Schemas** (JSON Schema style, implementable in code/UI)

**Heatmap Model** (per strategy):
```json
{
  "type": "object",
  "properties": {
    "ts": {"type": "number"},
    "symbol": {"type": "string"},
    "epoch": {"type": "string"},
    "version": {"type": "string", "const": "1.0"},
    "tiles": {
      "type": "object",
      "patternProperties": {
        "^[0-9]+$": {  // strike as string key
          "type": "object",
          "patternProperties": {
            "^(single|[0-9]+)$": {  // width or "single"
              "type": "object",
              "properties": {
                "value": {"type": "number"},
                "metadata": {
                  "type": "object",
                  "properties": {
                    "legs": {"type": "array"},
                    "tos_script": {"type": "string"}
                  }
                }
              },
              "required": ["value"]
            }
          }
        }
      }
    }
  },
  "required": ["ts", "symbol", "epoch", "tiles"]
}
```

**GEX Model** (calls/puts separate):
```json
{
  "type": "object",
  "properties": {
    "ts": {"type": "number"},
    "symbol": {"type": "string"},
    "expirations": {
      "type": "object",
      "patternProperties": {
        "^.*$": {  // expiration date
          "type": "object",
          "patternProperties": {
            "^[0-9]+$": {"type": "number"}  // strike → gex
          }
        }
      }
    }
  },
  "required": ["ts", "symbol", "expirations"]
}
```

**Next Steps**
- Add schema validation in builder before publish.
- Version field for evolution.
- UI type definitions from same schema.

