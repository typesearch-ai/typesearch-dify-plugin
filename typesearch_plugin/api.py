"""El cliente HTTP de la API de typesearch, lo justo para las tres herramientas y la validación de la clave.

HTTP directo con httpx en lugar del SDK ``typesearch``: el SDK todavía no está en PyPI, y un plugin que
dependa de él no se instalaría hasta que se publique. httpx ya viene con dify_plugin, así que el plugin
no suma nada a instalar.

Los errores de la API (RFC 9457, problem+json) se convierten en ``TypesearchError`` con su ``code``; el
mensaje nunca lleva la clave. Reintenta una vez los 408, 409, 429 y 5xx y los cortes de conexión, sólo si
entra en el tiempo de la llamada (Dify corta una herramienta a los 120 s).
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Mapping
from typing import Any

import httpx

from . import VERSION

BASE_URL = "https://api.typesearch.ai"
# Sin https:// a propósito: el análisis del Marketplace cuenta cada URL del código como un dominio al que
# el plugin se conecta, y el plugin sólo se conecta a api.typesearch.ai (manifest.yaml, network.domains).
DASHBOARD = "app.typesearch.ai"
USER_AGENT = f"typesearch-dify-plugin/{VERSION}"

TIMEOUT = 70.0  # una búsqueda deep puede tardar cerca de un minuto
BUDGET = 100.0  # el total de una llamada, reintentos incluidos: por debajo del límite de Dify
MAX_RETRIES = 1
MAX_RETRY_AFTER = 10.0  # si la API pide esperar más, se le dice al modelo en lugar de esperar

sleep = time.sleep  # las pruebas lo reemplazan para no esperar


class TypesearchError(Exception):
    """Un error de la API, de la red o de la configuración, listo para el modelo.

    ``code`` es estable (``invalid_api_key``, ``rate_limited``…); ``message`` es para personas.
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int | None = None,
        request_id: str | None = None,
        retry_after: float | None = None,
        errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.request_id = request_id
        self.retry_after = retry_after
        self.errors = errors or []

    def for_model(self) -> str:
        """``Error (code): message. Retry after N s. [request id]``: lo mismo que responde el MCP."""
        text = f"Error ({self.code}): {self.message}"
        others = [f"{e.get('path')}: {str(e.get('message')).rstrip('.')}" for e in self.errors[1:] if isinstance(e, Mapping)]
        if others:
            text += f" Also: {'; '.join(others)}."
        if self.retry_after is not None:
            text += f" Retry after {_seconds(self.retry_after)} s."
        if self.request_id:
            text += f" [request {self.request_id}]"
        return text


def missing_key() -> TypesearchError:
    return TypesearchError(
        "missing_api_key",
        f"Missing API key. Add your typesearch API key to this plugin's credentials in Dify. Get one at {DASHBOARD}.",
    )


class Client:
    """Un cliente por llamada: ``with Client(key) as c: c.search({...})``."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        budget: float | None = None,
        max_retries: int = MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        api_key = (api_key or "").strip()
        if not api_key:
            raise missing_key()
        self._key = api_key
        self._base_url = (base_url or BASE_URL).rstrip("/")
        self._timeout = TIMEOUT if timeout is None else timeout
        self._budget = BUDGET if budget is None else budget
        self._max_retries = max_retries
        self._http = httpx.Client(
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Accept-Language": "en",
                "User-Agent": USER_AGENT,
            },
        )

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    # --- Las rutas ----------------------------------------------------------------------------

    def search(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/search", json=body)

    def similar(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/similar", json=body)

    def contents(self, body: Mapping[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/contents", json=body)

    def usage(self) -> dict[str, Any]:
        """Gratis: el uso y los límites de la clave. Sirve para validarla al guardarla en Dify."""
        return self._request("GET", "/v1/usage")

    # --- El pedido, con reintentos --------------------------------------------------------------

    def _request(self, method: str, path: str, *, json: Mapping[str, Any] | None = None) -> dict[str, Any]:
        start = time.monotonic()
        attempt = 0
        while True:
            left = self._budget - (time.monotonic() - start)
            retry_after: float | None = None
            try:
                response = self._http.request(
                    method,
                    f"{self._base_url}{path}",
                    json=json,
                    timeout=httpx.Timeout(max(1.0, min(self._timeout, left)), connect=min(10.0, self._timeout)),
                )
            except (httpx.ConnectError, httpx.ConnectTimeout):
                # El pedido no llegó: se puede repetir sin riesgo de cobrarlo dos veces.
                error = TypesearchError("connection", "could not reach the typesearch API. Check the network connection and try again.")
            except httpx.TimeoutException:
                # La API lo estaba atendiendo: no se repite.
                raise TypesearchError("timeout", "typesearch took too long to answer. Try again, or use a lighter mode.") from None
            except httpx.TransportError:
                raise TypesearchError("connection", "the connection to the typesearch API was interrupted. Try again.") from None
            else:
                if response.status_code < 400:
                    return self._json(response)
                error = self._problem(response)
                if not _should_retry(response.status_code, error.code):
                    raise error
                retry_after = error.retry_after

            if attempt >= self._max_retries or (retry_after is not None and retry_after > MAX_RETRY_AFTER):
                raise error
            delay = retry_after if retry_after is not None else _backoff(attempt)
            # Sólo si al reintento le queda tiempo para contestar dentro de la llamada.
            if time.monotonic() - start + delay + min(self._timeout, 30.0) > self._budget:
                raise error
            sleep(delay)
            attempt += 1

    def _json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise TypesearchError(
                "invalid_response",
                f"the typesearch API answered with something that is not JSON (status {response.status_code}). Try again.",
                status=response.status_code,
                request_id=response.headers.get("x-request-id"),
            )
        return data

    def _problem(self, response: httpx.Response) -> TypesearchError:
        """Un problem+json de la API; si no lo es (un proxy, un corte), un error genérico con el estado."""
        try:
            problem = response.json()
        except ValueError:
            problem = None
        if not isinstance(problem, dict):
            problem = {}
        status = response.status_code
        code = str(problem.get("code") or _generic_code(status))
        message = str(problem.get("detail") or problem.get("title") or _generic_message(status))
        errors = problem.get("errors")
        return TypesearchError(
            code,
            _redact(message, self._key),
            status=status,
            request_id=problem.get("request_id") or response.headers.get("x-request-id"),
            retry_after=_retry_after(response.headers.get("retry-after")) if status in (429, 503) else None,
            errors=[
                {"path": str(e.get("path")), "message": _redact(str(e.get("message")), self._key)} for e in errors if isinstance(e, dict)
            ]
            if isinstance(errors, list)
            else None,
        )


# --- Utilidades --------------------------------------------------------------------------------


def _should_retry(status: int, code: str) -> bool:
    """Como los SDKs: 408, 409, 429 y 5xx; la cuota diaria no, porque vuelve a las 00:00 UTC."""
    if code == "quota_exceeded":
        return False
    return status in (408, 409, 429) or status >= 500


def _backoff(attempt: int) -> float:
    return min(0.5 * 2.0**attempt, 4.0) * (1 - random.random() * 0.25)


def _retry_after(value: str | None) -> float | None:
    """``Retry-After`` en segundos (la API no manda fechas)."""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def _seconds(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _generic_code(status: int) -> str:
    return {401: "unauthorized", 402: "payment_required", 403: "forbidden", 404: "not_found", 429: "rate_limited"}.get(
        status, f"http_{status}"
    )


def _generic_message(status: int) -> str:
    if status >= 500:
        return f"the typesearch API failed (status {status}). Try again in a moment."
    return f"the typesearch API answered with status {status}."


def _redact(text: str, key: str) -> str:
    """Por las dudas: la clave nunca llega a un mensaje."""
    return text.replace(key, "***") if key else text
