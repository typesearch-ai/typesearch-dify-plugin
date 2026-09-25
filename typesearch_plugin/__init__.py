"""typesearch para Dify: la lógica de las herramientas, aparte del pegamento con Dify.

- ``api``: el cliente HTTP de la API REST de typesearch (con httpx, que dify_plugin ya trae).
- ``params``: lee y valida los parámetros de cada herramienta, con errores escritos para el modelo.
- ``output``: la salida compacta, la misma que la del servidor MCP de typesearch.
- ``run``: corre una herramienta y convierte el resultado (o el error) en mensajes de Dify.

Todo lo que ve el usuario o el modelo, en inglés.
"""

VERSION = "0.1.0"
