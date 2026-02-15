"""
Distribution Core v1.0.0 — Versioning

Semantic versioning for metric bundles. Every DistributionResult carries
a version tag so consumers can detect formula changes.

Version policy:
    - Patch (0.0.x): Bug fixes, no formula changes.
    - Minor (0.x.0): New metrics added, existing unchanged.
    - Major (x.0.0): Formula change, bound change, or metric removal.

Frozen bounds and weights are part of the version contract.
Changing normalization bounds or CII weights requires a major version bump.
"""


class MetricVersion:
    """
    Version tagging for Distribution Core metric bundles.

    All results carry the version string so downstream consumers
    (Edge Lab, SEE, ALE, AOL) can detect and adapt to formula changes.
    """

    CURRENT = "1.0.0"

    def current_version(self) -> str:
        """Return the current Distribution Core version string."""
        return self.CURRENT


class VersionedBundle:
    """
    Utility for version-aware result validation.

    Consumers can check compatibility before processing a DistributionResult.
    """

    @staticmethod
    def is_compatible(result_version: str, expected_major: int = 1) -> bool:
        """
        Check if a result version is compatible with expected major version.

        Compatible means same major version (per semver).
        """
        try:
            parts = result_version.split(".")
            major = int(parts[0])
            return major == expected_major
        except (IndexError, ValueError):
            return False

    @staticmethod
    def parse(version_str: str) -> tuple[int, int, int]:
        """Parse semver string into (major, minor, patch) tuple."""
        parts = version_str.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid version format: {version_str}")
        return int(parts[0]), int(parts[1]), int(parts[2])
