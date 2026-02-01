"""
Atlas Remote Policy

Controls access to remote resources.
Remote access is disabled by default - explicit opt-in required.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RemotePolicy:
    """
    Policy governing remote artifact access.

    Default is restrictive: no remote access allowed.
    Must be explicitly enabled with clear constraints.
    """

    # Master switch - False by default
    allow_remote_access: bool = False

    # Rate limiting
    max_remote_calls: int = 10

    # Freshness
    freshness_window_seconds: int = 86400  # 24 hours

    # Domain restrictions (None = no allowlist enforcement)
    required_domains_allowlist: Optional[list[str]] = None

    # Identification
    user_agent: str = "Atlas-Core/0.1 (Knowledge Infrastructure)"

    # Timeout per request (seconds)
    request_timeout_seconds: float = 30.0

    # Tracking
    calls_made: int = field(default=0, repr=False)

    def can_access(self, url: str) -> tuple[bool, str]:
        """
        Check if URL can be accessed under this policy.

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Master switch
        if not self.allow_remote_access:
            return False, "Remote access is disabled by policy"

        # Rate limit
        if self.calls_made >= self.max_remote_calls:
            return False, (
                f"Remote call limit exceeded: "
                f"{self.calls_made}/{self.max_remote_calls}"
            )

        # Domain allowlist
        if self.required_domains_allowlist is not None:
            domain = self._extract_domain(url)
            if domain not in self.required_domains_allowlist:
                return False, (
                    f"Domain '{domain}' not in allowlist: "
                    f"{self.required_domains_allowlist}"
                )

        return True, "Access permitted"

    def record_call(self) -> None:
        """Record that a remote call was made."""
        self.calls_made += 1

    def reset_calls(self) -> None:
        """Reset call counter."""
        self.calls_made = 0

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        # Simple extraction without external dependencies
        url = url.lower()
        if "://" in url:
            url = url.split("://", 1)[1]
        if "/" in url:
            url = url.split("/", 1)[0]
        if ":" in url:
            url = url.split(":", 1)[0]
        return url

    @classmethod
    def permissive(
        cls,
        max_calls: int = 50,
        domains: Optional[list[str]] = None,
    ) -> "RemotePolicy":
        """Create a permissive policy for explicit remote work."""
        return cls(
            allow_remote_access=True,
            max_remote_calls=max_calls,
            required_domains_allowlist=domains,
        )

    @classmethod
    def strict(cls) -> "RemotePolicy":
        """Create strict policy - no remote access."""
        return cls(allow_remote_access=False)


def estimate_source_reliability(url: str, allowlist: list[str] = None) -> float:
    """
    Estimate source reliability heuristically.

    Higher for known/allowlisted domains.
    Lower for unknown sources.

    Returns:
        Reliability score 0.0 to 1.0
    """
    domain = RemotePolicy()._extract_domain(url)

    # Allowlisted domains get higher reliability
    if allowlist and domain in allowlist:
        return 0.8

    # Well-known documentation sites
    trusted_domains = {
        "github.com": 0.75,
        "docs.python.org": 0.85,
        "pypi.org": 0.8,
        "npmjs.com": 0.75,
        "readthedocs.io": 0.8,
        "docs.microsoft.com": 0.85,
        "developer.mozilla.org": 0.85,
    }

    for trusted, score in trusted_domains.items():
        if trusted in domain:
            return score

    # Unknown sources
    return 0.4


def estimate_volatility(url: str, content_type: str = "") -> float:
    """
    Estimate content volatility heuristically.

    News/blogs = high volatility (content changes frequently)
    Documentation = low volatility (content is stable)

    Returns:
        Volatility score 0.0 to 1.0
    """
    url_lower = url.lower()

    # High volatility indicators
    high_vol_patterns = [
        "news", "blog", "feed", "latest", "update",
        "twitter", "reddit", "status", "live",
    ]
    for pattern in high_vol_patterns:
        if pattern in url_lower:
            return 0.9

    # Low volatility indicators
    low_vol_patterns = [
        "docs", "documentation", "reference", "spec",
        "api", "manual", "guide", "stable", "archive",
    ]
    for pattern in low_vol_patterns:
        if pattern in url_lower:
            return 0.2

    # GitHub raw content
    if "raw.githubusercontent.com" in url_lower:
        return 0.4

    # Default moderate volatility
    return 0.5
