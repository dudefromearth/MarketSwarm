#!/usr/bin/env python3
"""
playbook_loader.py — Dynamic Playbook Loading for Vexy

Loads playbooks from markdown files in addition to the hardcoded manifest.
This allows users to add new playbooks without code changes.

Playbook Directory Structure:
  ~/.fotw/playbooks/           (default, can be overridden)
  └── tactical-0dte.md
  └── my-custom-playbook.md
  └── ...

Playbook Markdown Format:
  ---
  name: My Custom Playbook
  scope: Strategy          # Routine, Process, Strategy, App, Retrospective, Meta
  description: Brief description for Vexy
  min_tier: navigator      # observer, activator, navigator, administrator
  keywords: keyword1, keyword2, keyword3
  ---

  # Playbook Content

  The rest of the markdown is the playbook content...
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# Import the base Playbook dataclass
from .playbook_manifest import Playbook, PLAYBOOKS as HARDCODED_PLAYBOOKS


# =============================================================================
# CONFIGURATION
# =============================================================================

# Default playbook directories to scan (in order)
DEFAULT_PLAYBOOK_DIRS = [
    Path.home() / ".fotw" / "playbooks",
    Path("/Users/ernie/path"),  # User's Path directory
]

# Environment variable to override playbook directory
PLAYBOOK_DIR_ENV = "VEXY_PLAYBOOK_DIR"


# =============================================================================
# FRONTMATTER PARSING
# =============================================================================

def parse_frontmatter(content: str) -> tuple[Dict[str, Any], str]:
    """
    Parse YAML-like frontmatter from markdown content.

    Returns:
        Tuple of (metadata_dict, remaining_content)
    """
    # Check for frontmatter delimiter
    if not content.startswith("---"):
        return {}, content

    # Find closing delimiter
    lines = content.split("\n")
    end_idx = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return {}, content

    # Parse frontmatter
    frontmatter_lines = lines[1:end_idx]
    metadata = {}

    for line in frontmatter_lines:
        if ":" in line:
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()

            # Handle keywords as list
            if key == "keywords":
                metadata[key] = [kw.strip().lower() for kw in value.split(",")]
            else:
                metadata[key] = value

    # Remaining content
    remaining = "\n".join(lines[end_idx + 1:]).strip()

    return metadata, remaining


def extract_title_from_content(content: str) -> Optional[str]:
    """Extract title from first H1 heading if no name in frontmatter."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        # Remove emoji prefixes
        title = re.sub(r"^[🌿🎯📌⚙️🧠💡]+\s*", "", match.group(1))
        return title.strip()
    return None


def extract_keywords_from_content(content: str, max_keywords: int = 10) -> List[str]:
    """Extract likely keywords from content if not specified."""
    # Common trading/strategy terms to look for
    potential_keywords = [
        "butterfly", "fly", "spread", "calendar", "diagonal",
        "0dte", "dte", "expiration", "gamma", "theta", "vega",
        "vix", "volatility", "regime", "goldilocks", "chaos",
        "batman", "convexity", "asymmetric", "risk", "sizing",
        "entry", "exit", "management", "journal", "routine",
        "morning", "evening", "weekly", "monthly", "retrospective",
    ]

    content_lower = content.lower()
    found = []
    for kw in potential_keywords:
        if kw in content_lower and kw not in found:
            found.append(kw)
            if len(found) >= max_keywords:
                break

    return found


# =============================================================================
# PLAYBOOK LOADING
# =============================================================================

@dataclass
class LoadedPlaybook:
    """Extended Playbook with content and source info."""
    playbook: Playbook
    content: str
    source_file: Optional[Path] = None


def load_playbook_from_file(file_path: Path) -> Optional[LoadedPlaybook]:
    """
    Load a single playbook from a markdown file.

    Expected format:
    - Frontmatter with name, scope, description, min_tier, keywords
    - Or: auto-extract from content
    """
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None

    metadata, body = parse_frontmatter(content)

    # Extract or default values
    name = metadata.get("name") or metadata.get("title")
    if not name:
        name = extract_title_from_content(content)
    if not name:
        # Use filename
        name = file_path.stem.replace("-", " ").replace("_", " ").title()

    # Clean name (remove emoji and version numbers for matching)
    clean_name = re.sub(r"[🌿🎯📌⚙️🧠💡]+\s*", "", name)
    clean_name = re.sub(r"\s+v\d+\.?\d*$", "", clean_name, flags=re.IGNORECASE)

    scope = metadata.get("scope", "Strategy")
    description = metadata.get("description", f"Playbook: {clean_name}")
    min_tier = metadata.get("min_tier", "navigator")

    keywords = metadata.get("keywords", [])
    if not keywords:
        keywords = extract_keywords_from_content(content)

    # Add name words as keywords
    name_words = [w.lower() for w in clean_name.split() if len(w) > 2]
    keywords = list(set(keywords + name_words))

    playbook = Playbook(
        name=clean_name.strip(),
        scope=scope,
        description=description,
        min_tier=min_tier,
        keywords=keywords,
    )

    return LoadedPlaybook(
        playbook=playbook,
        content=content,
        source_file=file_path,
    )


def scan_playbook_directory(directory: Path) -> List[LoadedPlaybook]:
    """Scan a directory for playbook markdown files."""
    playbooks = []

    if not directory.exists():
        return playbooks

    for file_path in directory.glob("*.md"):
        # Skip README and other non-playbook files
        if file_path.name.lower() in ["readme.md", "index.md"]:
            continue

        loaded = load_playbook_from_file(file_path)
        if loaded:
            playbooks.append(loaded)

    return playbooks


def get_playbook_directories() -> List[Path]:
    """Get list of directories to scan for playbooks."""
    dirs = []

    # Check environment variable first
    env_dir = os.getenv(PLAYBOOK_DIR_ENV)
    if env_dir:
        dirs.append(Path(env_dir))

    # Add default directories
    dirs.extend(DEFAULT_PLAYBOOK_DIRS)

    return dirs


# =============================================================================
# UNIFIED PLAYBOOK ACCESS
# =============================================================================

# Cache for loaded playbooks
_loaded_playbooks_cache: Optional[List[LoadedPlaybook]] = None
_cache_loaded = False


def load_all_playbooks(force_reload: bool = False) -> List[LoadedPlaybook]:
    """
    Load all playbooks from hardcoded manifest and file system.

    Returns list of LoadedPlaybook objects.
    """
    global _loaded_playbooks_cache, _cache_loaded

    if _cache_loaded and not force_reload:
        return _loaded_playbooks_cache or []

    all_playbooks = []
    seen_names = set()

    # Load from file system first (allows overriding hardcoded)
    for directory in get_playbook_directories():
        for loaded in scan_playbook_directory(directory):
            name_lower = loaded.playbook.name.lower()
            if name_lower not in seen_names:
                all_playbooks.append(loaded)
                seen_names.add(name_lower)

    # Add hardcoded playbooks (if not already loaded from files)
    for pb in HARDCODED_PLAYBOOKS:
        name_lower = pb.name.lower()
        if name_lower not in seen_names:
            all_playbooks.append(LoadedPlaybook(
                playbook=pb,
                content="",  # No content for hardcoded
                source_file=None,
            ))
            seen_names.add(name_lower)

    _loaded_playbooks_cache = all_playbooks
    _cache_loaded = True

    return all_playbooks


def get_all_playbooks() -> List[Playbook]:
    """Get all playbooks (both hardcoded and file-based)."""
    return [lp.playbook for lp in load_all_playbooks()]


def get_playbook_content(name: str) -> Optional[str]:
    """Get the full content of a playbook by name."""
    name_lower = name.lower()
    for lp in load_all_playbooks():
        if lp.playbook.name.lower() == name_lower:
            return lp.content
    return None


def get_playbook_with_content(name: str) -> Optional[LoadedPlaybook]:
    """Get playbook with its content by name."""
    name_lower = name.lower()
    for lp in load_all_playbooks():
        if lp.playbook.name.lower() == name_lower:
            return lp
    return None


def reload_playbooks() -> int:
    """
    Force reload all playbooks from disk.

    Returns count of loaded playbooks.
    """
    global _cache_loaded
    _cache_loaded = False
    playbooks = load_all_playbooks(force_reload=True)
    return len(playbooks)


# =============================================================================
# ENHANCED LOOKUP FUNCTIONS (Override manifest functions)
# =============================================================================

def get_playbooks_for_tier_dynamic(tier: str) -> List[Playbook]:
    """Get all playbooks accessible at a given tier (including file-based)."""
    tier_order = ["observer", "activator", "navigator", "coaching", "administrator"]
    tier_idx = tier_order.index(tier.lower()) if tier.lower() in tier_order else 0

    accessible = []
    for lp in load_all_playbooks():
        pb = lp.playbook
        pb_idx = tier_order.index(pb.min_tier) if pb.min_tier in tier_order else 0
        if tier_idx >= pb_idx:
            accessible.append(pb)

    return accessible


def find_relevant_playbooks_dynamic(query: str, tier: str, max_results: int = 3) -> List[Playbook]:
    """
    Find playbooks relevant to a user query (including file-based).
    """
    query_lower = query.lower()
    accessible = get_playbooks_for_tier_dynamic(tier)

    # Score by keyword matches
    scored = []
    for pb in accessible:
        score = sum(1 for kw in pb.keywords if kw in query_lower)
        # Boost if name matches
        if any(word in query_lower for word in pb.name.lower().split()):
            score += 2
        if score > 0:
            scored.append((score, pb))

    # Sort by score descending
    scored.sort(key=lambda x: -x[0])

    return [pb for _, pb in scored[:max_results]]


# =============================================================================
# INITIALIZATION
# =============================================================================

def ensure_playbook_directory():
    """Ensure the default playbook directory exists."""
    default_dir = Path.home() / ".fotw" / "playbooks"
    default_dir.mkdir(parents=True, exist_ok=True)

    # Create a README if it doesn't exist
    readme = default_dir / "README.md"
    if not readme.exists():
        readme.write_text("""# Vexy Playbooks

Place your playbook markdown files in this directory.

## Format

Each playbook should be a `.md` file with frontmatter:

```markdown
---
name: My Playbook Name
scope: Strategy
description: Brief description for Vexy
min_tier: navigator
keywords: keyword1, keyword2, keyword3
---

# Playbook Content

Your playbook content here...
```

## Fields

- **name**: Display name (or extracted from first H1)
- **scope**: Routine, Process, Strategy, App, Retrospective, Meta
- **description**: Brief description shown in chat
- **min_tier**: Minimum access tier (observer, activator, navigator, administrator)
- **keywords**: Comma-separated keywords for matching queries

## Example

See existing playbooks in `/Users/ernie/path/` for examples.
""")

    return default_dir
