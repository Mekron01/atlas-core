"""
Atlas WebEye

Read-only observer for web URLs.
No crawling, no link following, no silent updates.
"""

import hashlib
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


class WebEye:
    """
    Web observer that fetches single URLs.

    Rules:
    - No crawling or link following
    - Respects RemotePolicy strictly
    - Emits REMOTE_LOOKUP_DECLINED if access denied
    - All fetched data marked as remote with decay metadata
    """

    def __init__(self, writer):
        """
        Initialize WebEye.

        Args:
            writer: EventWriter for emitting events
        """
        self.writer = writer
        self.module_name = "WebEye"

    def _make_event_id(self) -> str:
        """Generate unique event ID."""
        return f"web-{uuid.uuid4().hex[:16]}"

    def can_handle(self, locator: str) -> bool:
        """Check if this eye can handle the locator."""
        locator_lower = locator.lower()
        return (
            locator_lower.startswith("http://")
            or locator_lower.startswith("https://")
        )

    def enumerate(self, locator: str) -> list[str]:
        """
        Enumerate candidates from locator.

        WebEye does NOT crawl - returns only the exact URL.
        """
        if not self.can_handle(locator):
            return []
        return [locator]

    def observe(
        self,
        url: str,
        budget,
        remote_policy: RemotePolicy,
        session_id: Optional[str] = None,
    ) -> dict:
        """
        Observe a single URL.

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

        # Check time budget
        max_time_ms = getattr(budget, "max_time_ms", None) or float("inf")
        max_bytes = getattr(budget, "max_bytes_per_artifact", None)
        if max_bytes is None:
            max_bytes = getattr(budget, "max_bytes", None) or 1_000_000

        # Fetch URL
        try:
            remote_policy.record_call()

            req = Request(
                url,
                headers={"User-Agent": remote_policy.user_agent},
            )

            with urlopen(
                req,
                timeout=remote_policy.request_timeout_seconds,
            ) as response:
                # Check time budget
                elapsed_ms = (time.time() - start_time) * 1000
                if elapsed_ms > max_time_ms:
                    self._emit_access_limitation(
                        url=url,
                        reason="Time budget exceeded during fetch",
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

                # Read limited bytes
                content = response.read(max_bytes)
                content_length = len(content)

                # Get metadata
                http_status = response.status
                content_type = response.headers.get(
                    "Content-Type", "application/octet-stream"
                )

                # Check if truncated
                truncated = False
                full_length = response.headers.get("Content-Length")
                if full_length:
                    try:
                        if int(full_length) > content_length:
                            truncated = True
                    except ValueError:
                        pass

        except HTTPError as e:
            self._emit_access_limitation(
                url=url,
                reason=f"HTTP error: {e.code} {e.reason}",
                limit_type="http_error",
                limit_value=0,
                current_value=e.code,
                session_id=session_id,
            )
            return {
                "status": "http_error",
                "reason": f"{e.code} {e.reason}",
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
            self._emit_access_limitation(
                url=url,
                reason=f"Fetch failed: {str(e)}",
                limit_type="exception",
                limit_value=0,
                current_value=0,
                session_id=session_id,
            )
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

        # Emit ARTIFACT_SEEN
        self._emit_artifact_seen(
            artifact_id=artifact_id,
            url=url,
            size=content_length,
            content_type=content_type,
            remote_meta=remote_meta,
            session_id=session_id,
        )

        # Emit FINGERPRINT_COMPUTED
        self._emit_fingerprint_computed(
            artifact_id=artifact_id,
            content_hash=content_hash,
            size_bytes=content_length,
            session_id=session_id,
        )

        # Emit EXTRACTION_PERFORMED
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

        # Emit limitation if truncated
        if truncated:
            self._emit_access_limitation(
                url=url,
                reason="Content truncated due to byte limit",
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

    def _extract_text_excerpt(
        self,
        content: bytes,
        content_type: str,
        max_length: int = 500,
    ) -> str:
        """Extract text excerpt from content."""
        try:
            # Try UTF-8 first
            text = content.decode("utf-8", errors="replace")
        except Exception:
            text = content.decode("latin-1", errors="replace")

        # Clean and truncate
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
                "source_type": "web",
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
