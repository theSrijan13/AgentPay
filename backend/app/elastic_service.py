"""Optional Elastic-backed audit/event search with a safe in-memory fallback.

Never send payment credentials, raw buyer prompts, or PayPal request/response bodies
into telemetry. Instrumentation errors must not break shopping or checkout.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

try:
    from elasticsearch import AsyncElasticsearch
except ImportError:  # Allows the API to boot in minimal local environments.
    AsyncElasticsearch = None  # type: ignore[assignment,misc]


class ElasticTelemetry:
    def __init__(self) -> None:
        self.client: Any = None
        self.connected = False
        self.last_error: str | None = None
        self.memory_events: list[dict[str, Any]] = []
        self.index_name = f"{settings.elastic_index_prefix.strip().lower() or 'agentpay'}-events"

    @property
    def configured(self) -> bool:
        return bool(settings.elasticsearch_url.strip() and settings.elastic_api_key.strip())

    @staticmethod
    def _safe_error_hint(exc: Exception) -> str:
        """Return actionable diagnostics without revealing the endpoint credentials."""
        status = getattr(getattr(exc, "meta", None), "status", None)
        name = type(exc).__name__
        if status in (401, 403) or "Authentication" in name or "Authorization" in name:
            return "Authentication/authorization failed; verify the Elasticsearch API key and index permissions."
        if status == 404:
            return "Elasticsearch returned HTTP 404; verify ELASTICSEARCH_URL is the Elasticsearch endpoint, not the Kibana URL."
        if status and status >= 500:
            return f"Elasticsearch returned HTTP {status}; retry after checking the deployment status."
        if "Connection" in name or "Timeout" in name or "Tls" in name:
            return "Could not connect securely; verify the Elasticsearch endpoint URL, network access, and TLS configuration."
        return f"Elastic connection check failed ({name}); verify the endpoint, API key, and index permissions."

    async def start(self) -> None:
        self.connected = False
        self.last_error = None
        if not self.configured:
            self.last_error = "Elastic is not configured. Add ELASTICSEARCH_URL and ELASTIC_API_KEY to backend/.env, then restart FastAPI."
            logger.info("Elastic telemetry is not configured; using in-memory event history.")
            return
        if AsyncElasticsearch is None:
            self.last_error = "The elasticsearch async client is not installed. Install backend requirements and restart FastAPI."
            logger.warning(self.last_error)
            return
        try:
            if self.client is None:
                self.client = AsyncElasticsearch(
                    settings.elasticsearch_url.strip(),
                    api_key=settings.elastic_api_key.strip(),
                    request_timeout=4,
                    max_retries=0,
                    retry_on_timeout=False,
                )
            # info() surfaces authentication/HTTP errors; ping() only returns False
            # and hides the reason, which made the dashboard's OFFLINE state ambiguous.
            await self.client.info()
            self.connected = True
            self.last_error = None
            logger.info("Elastic telemetry connected; index=%s", self.index_name)
        except Exception as exc:  # pragma: no cover - external service failure
            self.connected = False
            self.last_error = self._safe_error_hint(exc)
            logger.warning("Elastic startup check failed (%s); using in-memory event history.", type(exc).__name__)

    async def reconnect(self) -> None:
        """Close and retry with settings loaded at process startup."""
        if self.client is not None:
            try:
                await self.client.close()
            except Exception:
                logger.debug("Elastic client close failed during reconnect", exc_info=True)
        self.client = None
        self.connected = False
        await self.start()

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.close()
            except Exception:
                logger.debug("Elastic client close failed", exc_info=True)
        self.client = None
        self.connected = False

    async def record(
        self,
        event_type: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        safe_details = details if isinstance(details, dict) else {}
        event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "application": "agentpay",
            "event_type": str(event_type)[:80],
            "message": str(message)[:500],
            "details": safe_details,
        }
        self.memory_events.append(event)
        if len(self.memory_events) > 500:
            del self.memory_events[:-500]

        if self.client is not None:
            started = time.monotonic()
            try:
                await self.client.index(
                    index=self.index_name,
                    id=event["event_id"],
                    document=event,
                    refresh=False,
                )
                self.connected = True
                self.last_error = None
            except Exception as exc:  # telemetry is best effort
                self.connected = False
                self.last_error = self._safe_error_hint(exc)
                logger.warning(
                    "Elastic event indexing failed (%s, %.0fms); retained in memory.",
                    type(exc).__name__, (time.monotonic() - started) * 1000,
                )
        return event

    async def search(self, query: str = "", limit: int = 25) -> dict[str, Any]:
        limit = max(1, min(int(limit), 100))
        clean_query = query.strip()[:120]
        if self.client is not None and self.connected:
            try:
                elastic_query: dict[str, Any]
                if clean_query:
                    elastic_query = {
                        "multi_match": {
                            "query": clean_query,
                            "fields": ["event_type^2", "message", "details.source", "details.status", "details.merchant"],
                            "type": "best_fields",
                        }
                    }
                else:
                    elastic_query = {"match_all": {}}
                response = await self.client.search(
                    index=self.index_name,
                    query=elastic_query,
                    size=limit,
                    sort=[{"timestamp": {"order": "desc"}}],
                )
                body = response.body if hasattr(response, "body") else response
                hits = body.get("hits", {}).get("hits", [])
                return {"events": [hit.get("_source", {}) for hit in hits], "source": "elasticsearch"}
            except Exception as exc:  # index may not yet exist / permissions / network
                self.connected = False
                self.last_error = self._safe_error_hint(exc)
                logger.warning("Elastic event search failed (%s); using memory fallback.", type(exc).__name__)

        events = list(reversed(self.memory_events))
        if clean_query:
            needle = clean_query.casefold()
            events = [e for e in events if needle in (
                str(e.get("event_type", "")) + " " + str(e.get("message", "")) + " " + str(e.get("details", {}))
            ).casefold()]
        return {"events": events[:limit], "source": "memory"}

    def status(self) -> dict[str, Any]:
        if self.connected:
            message = "Elastic connected; AgentPay events are indexed for search."
        elif not self.configured:
            message = self.last_error or "Elastic is not configured. Set ELASTICSEARCH_URL and ELASTIC_API_KEY in backend/.env, then restart FastAPI."
        else:
            message = self.last_error or "Elastic is configured but not connected. Verify the Elasticsearch endpoint and API key, then retry."
        return {
            "configured": self.configured,
            "connected": self.connected,
            "event_store": "elasticsearch" if self.connected else "in_memory_fallback",
            "index": self.index_name if self.configured else None,
            "message": message,
            "last_error": self.last_error,
        }
