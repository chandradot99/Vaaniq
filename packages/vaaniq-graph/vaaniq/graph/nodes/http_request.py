"""
HttpRequestNode — call any external REST API or webhook.

This is the Tier 2 custom tool escape hatch. Use it for any API
that doesn't have a pre-built tool in vaaniq-tools.

Config:
    method            (str)   HTTP method: GET, POST, PUT, PATCH, DELETE
    url               (str)   endpoint URL — supports {{template}} syntax
    headers           (dict)  request headers — supports {{template}} syntax
    body              (dict)  JSON request body — supports {{template}} syntax
    params            (dict)  query params — supports {{template}} syntax
    save_response_to  (str)   state key to store the JSON response (optional)
    timeout_seconds   (int)   request timeout, default 10

On non-2xx response the node sets state["error"] and does not raise,
so the graph can route to an error handler node if one is defined.
"""
import httpx

from vaaniq.graph.nodes.base import BaseNode
from vaaniq.core.state import SessionState
from vaaniq.graph.resolver import TemplateResolver


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
            return {"error": f"HTTP {exc.response.status_code} from {url}: {exc.response.text[:200]}"}
        except httpx.RequestError as exc:
            return {"error": f"Request failed: {exc}"}

        if save_key:
            try:
                return {save_key: response.json()}
            except Exception:
                return {save_key: response.text}

        return {}
