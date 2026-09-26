from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from typesearch_plugin.run import check_credentials


class TypesearchProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # GET /v1/usage: una llamada gratis que dice si la clave sirve.
        problem = check_credentials(credentials)
        if problem:
            raise ToolProviderCredentialValidationError(problem)
