"""
HttpRequestNode — call any external REST API or webhook.

This is the Tier 2 custom tool escape hatch. Use it for any API
that doesn't have a pre-built tool in naaviq-tools.

Config:
    method            (str)   HTTP method: GET, POST, PUT, PATCH, DELETE
    url               (str)   endpoint URL — supports {{template}} syntax
    headers           (dict)  request headers — supports {{template}} syntax
    body              (dict)  JSON request body — supports {{template}} syntax
    params            (dict)  query params — supports {{template}} syntax
    save_response_to  (str)   state key to store the JSON response (optional)
    timeout_seconds   (int)   request timeout, default 10

On non-2xx response the node sets state["error"] and adds an agent message
to state["messages"] so the error is visible in the chat/test panel.
"""
import httpx
import structlog

from naaviq.core.state import SessionState
from naaviq.graph.nodes.base import PROTECTED_STATE_KEYS, BaseNode
from naaviq.graph.resolver import TemplateResolver

log = structlog.get_logger()


class HttpRequestNode(BaseNode):
    async def __call__(self, state: SessionState) -> dict:
        cfg = TemplateResolver.resolve(self.config, state, self.org_keys)
        method: str = cfg["method"].upper()
        url: str = cfg["url"]
        headers: dict = cfg.get("headers", {})
        body: dict | None = cfg.get("body")
        params: dict | None = cfg.get("params")
        timeout: int = int(cfg.get("timeout_seconds", 10))
        save_key: str | None = cfg.get("save_response_to")

        # Guard against writing into protected system keys
        if save_key and save_key in PROTECTED_STATE_KEYS:
            error_msg = f"save_response_to: '{save_key}' is a protected state key and cannot be overwritten."
            log.error("http_request_protected_key", key=save_key, url=url, session_id=state.get("session_id"))
            return {"error": error_msg}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    json=body,
                    params=params,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            error_msg = f"HTTP {exc.response.status_code} from {url}: {exc.response.text[:300]}"
            log.warning(
                "http_request_http_error", url=url, status=exc.response.status_code, session_id=state.get("session_id")
            )
            return {"error": error_msg}
        except httpx.RequestError as exc:
            error_msg = f"Request to {url} failed: {exc}"
            log.warning("http_request_error", url=url, error=str(exc), session_id=state.get("session_id"))
            return {"error": error_msg}

        if save_key:
            try:
                return {save_key: response.json()}
            except Exception:
                return {save_key: response.text}

        return {}
