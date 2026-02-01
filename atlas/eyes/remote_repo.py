"""
Atlas RemoteRepoEye

Read-only observer for remote repositories (GitHub, etc).
No crawling beyond manifest files.
"""

import hashlib
import re
import time
import uuid
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from atlas.remote.policy import (
    RemotePolicy,
    estimate_source_reliability,
    estimate_volatility,
)


class RemoteRepoEye:
    """
    Remote repository observer.

    Handles:
    - https://github.com/owner/repo
    - git+https://github.com/owner/repo

    Only fetches:
    - Repo root (via API or HTML)
    - README
    - Manifest files (pyproject.toml, requirements.txt, package.json)

    NO recursive crawling.
    """

    # Known manifest files to check
    MANIFEST_FILES = [
        "README.md",
        "README.rst",
        "README.txt",
        "README",
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "package.json",
        "Cargo.toml",
        "go.mod",
    ]

    def __init__(self, writer):
        """
        Initialize RemoteRepoEye.

        Args:
            writer: EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "RemoteRepoEye"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"repo-{uuid.uuid4().hex[:16]}"

    def can_handle(self, locator: str) -> bool:
        """Check if this eye can handle the locator."""
        locator_lower = locator.lower()
        return (
            locator_lower.startswith("https://github.com/")
            or locator_lower.startswith("git+https://")
        )

    def _parse_github_url(self, url: str) -> Optional[tuple[str, str]]:
        """Parse GitHub URL into (owner, repo)."""
        url = url.replace("git+https://", "https://")

        # Match github.com/owner/repo pattern
        match = re.match(
            r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?(?:/.*)?$",
            url,
        )
        if match:
            return match.group(1), match.group(2)
        return None

    def enumerate(self, locator: str) -> list[str]:
        """
        Enumerate candidates from repo locator.

        Only emits:
        - Repo root
        - README
        - Manifest files

        NO crawling beyond these.
        """
        if not self.can_handle(locator):
            return []

        parsed = self._parse_github_url(locator)
        if not parsed:
            return []

        owner, repo = parsed
        candidates = []

        # Repo root (API endpoint)
        candidates.append(f"https://api.github.com/repos/{owner}/{repo}")

        # Raw content URLs for known files
        base_raw = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD"

        for manifest in self.MANIFEST_FILES:
            candidates.append(f"{base_raw}/{manifest}")

        return candidates

    def observe(
        self,
        url: str,
        budget,
        remote_policy: RemotePolicy,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Observe a single URL from enumerated candidates.

        Args:
            url: URL to fetch
            budget: Budget constraints
            remote_policy: Remote access policy
            session_id: Optional session ID

        Returns:
            Result dict with status and artifact info
        """
        start_time = time.time()

        # Check policy
        allowed, reason = remote_policy.can_access(url)
        if not allowed:
            self._emit_remote_lookup_declined(
                url=url,
                reason=reason,
                session_id=session_id,
            )
            return {
                "status": "declined",
                "reason": reason,
                "artifact_id": None,
            }

        # Get budget limits
        max_time_ms = getattr(budget, "max_time_ms", None) or float("inf")
        max_bytes = getattr(budget, "max_bytes_per_artifact", None)
        if max_bytes is None:
            max_bytes = getattr(budget, "max_bytes", None) or 1_000_000

        # Fetch URL
        try:
            remote_policy.record_call()

            headers = {"User-Agent": remote_policy.user_agent}

            # Add Accept header for GitHub API
            if "api.github.com" in url:
                headers["Accept"] = "application/vnd.github.v3+json"

            req = Request(url, headers=headers)

            with urlopen(
                req,
                timeout=remote_policy.request_timeout_seconds,
            ) as response:
                # Check time
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms > max_time_ms:
                    self._emit_access_limitation(
                        url=url,
                        reason="Time budget exceeded",
                        limit_type="max_time_ms",
                        limit_value=max_time_ms,
                        current_value=elapsed_ms,
                        session_id=session_id,
                    )
                    return {
                        "status": "timeout",
                        "reason": "Time budget exceeded",
                        "artifact_id": None,
                    }

                content = response.read(max_bytes)
                content_length = len(content)
                http_status = response.status
                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )

                # Check truncation
                truncated = False
                full_length = response.headers.get("Content-Length")
                if full_length:
                    try:
                        if int(full_length) > content_length:
                            truncated = True
                    except ValueError:
                        pass

        except HTTPError as e:
            if e.code == 404:
                # File doesn't exist - not an error for optional manifests
                return {
                    "status": "not_found",
                    "reason": "Resource not found",
                    "artifact_id": None,
                }
            self._emit_access_limitation(
                url=url,
                reason=f"HTTP error: {e.code}",
                limit_type="http_error",
                limit_value=0,
                current_value=e.code,
                session_id=session_id,
            )
            return {
                "status": "http_error",
                "reason": f"{e.code}",
                "artifact_id": None,
            }

        except URLError as e:
            self._emit_access_limitation(
                url=url,
                reason=f"URL error: {e.reason}",
                limit_type="url_error",
                limit_value=0,
                current_value=0,
                session_id=session_id,
            )
            return {
                "status": "url_error",
                "reason": str(e.reason),
                "artifact_id": None,
            }

        except Exception as e:
            return {
                "status": "error",
                "reason": str(e),
                "artifact_id": None,
            }

        # Compute hash
        content_hash = hashlib.sha256(content).hexdigest()
        artifact_id = content_hash

        # Build remote metadata
        now = time.time()
        allowlist = remote_policy.required_domains_allowlist or []
        remote_meta = {
            "source_reliability": estimate_source_reliability(url, allowlist),
            "volatility_score": estimate_volatility(url, content_type),
            "freshness_window_seconds": remote_policy.freshness_window_seconds,
            "last_verified_at": now,
            "corroboration_count": 1,
        }

        # Emit events
        self._emit_artifact_seen(
            artifact_id=artifact_id,
            url=url,
            size=content_length,
            content_type=content_type,
            remote_meta=remote_meta,
            session_id=session_id,
        )

        self._emit_fingerprint_computed(
            artifact_id=artifact_id,
            content_hash=content_hash,
            size_bytes=content_length,
            session_id=session_id,
        )

        text_excerpt = self._extract_text_excerpt(content, content_type)
        self._emit_extraction_performed(
            artifact_id=artifact_id,
            url=url,
            http_status=http_status,
            content_type=content_type,
            text_excerpt=text_excerpt,
            remote_meta=remote_meta,
            session_id=session_id,
        )

        if truncated:
            self._emit_access_limitation(
                url=url,
                reason="Content truncated",
                limit_type="max_bytes",
                limit_value=max_bytes,
                current_value=content_length,
                session_id=session_id,
            )

        return {
            "status": "success",
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "size": content_length,
            "truncated": truncated,
        }

    def observe_repo(
        self,
        repo_url: str,
        budget,
        remote_policy: RemotePolicy,
        session_id: Optional[str] = None,
    ) -> list[dict]:
        """
        Observe a repository and its manifest files.

        Args:
            repo_url: Repository URL
            budget: Budget constraints
            remote_policy: Remote access policy
            session_id: Optional session ID

        Returns:
            List of result dicts for each observed file
        """
        results = []
        candidates = self.enumerate(repo_url)

        for candidate in candidates:
            result = self.observe(
                url=candidate,
                budget=budget,
                remote_policy=remote_policy,
                session_id=session_id,
            )
            results.append({
                "url": candidate,
                **result,
            })

            # Check if we've hit call limit
            if remote_policy.calls_made >= remote_policy.max_remote_calls:
                break

        return results

    def _extract_text_excerpt(
        self,
        content: bytes,
        content_type: str,
        max_length: int = 500,
    ) -> str:
        """Extract text excerpt from content."""
        try:
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = content.decode("latin-1", errors="replace")

        text = " ".join(text.split())[:max_length]
        if len(text) == max_length:
            text = text[:max_length - 3] + "..."

        return text

    def _emit_remote_lookup_declined(
        self,
        url: str,
        reason: str,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit REMOTE_LOOKUP_DECLINED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "REMOTE_LOOKUP_DECLINED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": None,
            "confidence": 1.0,
            "evidence_refs": [],
            "payload": {
                "locator": url,
                "reason": reason,
                "access_scope": "none",
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def _emit_artifact_seen(
        self,
        artifact_id: str,
        url: str,
        size: int,
        content_type: str,
        remote_meta: dict,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit ARTIFACT_SEEN event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "ARTIFACT_SEEN",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": 0.9 * remote_meta.get("source_reliability", 0.5),
            "evidence_refs": [],
            "payload": {
                "locator": url,
                "source_type": "remote_repo",
                "access_scope": "read-only",
                "size": size,
                "content_type": content_type,
                "remote": remote_meta,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def _emit_fingerprint_computed(
        self,
        artifact_id: str,
        content_hash: str,
        size_bytes: int,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit FINGERPRINT_COMPUTED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "FINGERPRINT_COMPUTED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": 1.0,
            "evidence_refs": [],
            "payload": {
                "content_hash": content_hash,
                "hash_algorithm": "sha256",
                "size_bytes": size_bytes,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def _emit_extraction_performed(
        self,
        artifact_id: str,
        url: str,
        http_status: int,
        content_type: str,
        text_excerpt: str,
        remote_meta: dict,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit EXTRACTION_PERFORMED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "EXTRACTION_PERFORMED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": artifact_id,
            "confidence": 0.8,
            "evidence_refs": [],
            "payload": {
                "depth": "shallow",
                "extracted_text_excerpt": text_excerpt,
                "metadata": {
                    "http_status": http_status,
                    "content_type": content_type,
                    "url": url,
                },
                "remote": remote_meta,
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id

    def _emit_access_limitation(
        self,
        url: str,
        reason: str,
        limit_type: str,
        limit_value: float,
        current_value: float,
        session_id: Optional[str] = None,
    ) -> str:
        """Emit ACCESS_LIMITATION_NOTED event."""
        event_id = self._make_event_id()

        event = {
            "event_id": event_id,
            "event_type": "ACCESS_LIMITATION_NOTED",
            "ts": time.time(),
            "actor": {"module": self.module_name},
            "artifact_id": None,
            "confidence": 1.0,
            "evidence_refs": [],
            "payload": {
                "locator": url,
                "reason": reason,
                "limit_type": limit_type,
                "limit_value": limit_value,
                "current_value": current_value,
                "access_scope": "read-only",
            },
        }

        if session_id:
            event["session_id"] = session_id

        self.writer.append(event)
        return event_id
