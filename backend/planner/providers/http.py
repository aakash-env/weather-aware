"""Small HTTP helper that never includes secrets in error text."""

import httpx

from planner.providers.base import ProviderError

USER_AGENT = "WeatherAwareTruck/1.0 (route planning; educational)"


def request_json(client: httpx.Client, url: str, params: dict, timeout: float) -> dict | list:
    try:
        response = client.get(
            url,
            params=params,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )
    except httpx.HTTPError as exc:
        raise ProviderError("The upstream request failed.") from exc
    if response.status_code >= 400:
        message = _safe_message(response)
        raise ProviderError(message)
    try:
        return response.json()
    except ValueError as exc:
        raise ProviderError("The upstream response was not JSON.") from exc


def _safe_message(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict):
        text = body.get("message") or body.get("reason") or body.get("code")
        if text:
            return f"Upstream returned {response.status_code}: {text}"
    return f"Upstream returned HTTP {response.status_code}."
