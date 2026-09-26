"""Prueba de humo del .difypkg con el runtime local del plugin daemon de Dify (``dify plugin run``).

    uv run python scripts/smoke.py path/to/dify-cli typesearch-0.1.0.difypkg

El daemon hace lo mismo que al instalar el plugin en Dify: valida el manifest y los YAML con sus reglas,
crea el entorno de Python desde requirements.txt (con uv) y levanta el plugin. Después le manda tres
pedidos que no llegan a la API (sin clave, un parámetro inválido y una clave vacía al validar) y revisa
las respuestas. Necesita uv y Python 3.12, y red para instalar las dependencias.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from typing import Any

REQUESTS: list[dict[str, Any]] = [
    {
        "invoke_id": "similar-without-key",
        "type": "tool",
        "action": "invoke_tool",
        "request": {
            "provider": "typesearch",
            "tool": "find_similar",
            "credentials": {},
            "tool_parameters": {"url": "https://diarioejemplo.example/economia/nota-1"},
        },
    },
    {
        "invoke_id": "search-invalid-query",
        "type": "tool",
        "action": "invoke_tool",
        "request": {
            "provider": "typesearch",
            "tool": "search_news",
            "credentials": {"typesearch_api_key": "ts_test_smoke"},
            "tool_parameters": {"query": "x"},
        },
    },
    {
        "invoke_id": "validate-empty-key",
        "type": "tool",
        "action": "validate_tool_credentials",
        "request": {"provider": "typesearch", "credentials": {"typesearch_api_key": ""}},
    },
]
EXPECTED = {
    "similar-without-key": "Error (missing_api_key): Missing API key.",
    "search-invalid-query": "Error (invalid_request): query needs at least two letters.",
    "validate-empty-key": "Enter your typesearch API key.",
}


def main(cli: str, package: str, timeout: float = 300) -> int:
    work = tempfile.mkdtemp(prefix="typesearch-smoke-")
    env = {**os.environ, "TMPDIR": work}
    if not env.get("PYTHON_INTERPRETER_PATH"):
        env["PYTHON_INTERPRETER_PATH"] = shutil.which("python3.12") or sys.executable
    for r in REQUESTS:
        r["request"] = {"type": r["type"], "action": r["action"], "user_id": "smoke", **r["request"]}
    proc = subprocess.Popen(
        [cli, "plugin", "run", package, "-r", "json"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    assert proc.stdin and proc.stdout and proc.stderr
    stderr: list[str] = []
    threading.Thread(target=lambda: stderr.extend(proc.stderr), daemon=True).start()  # type: ignore[arg-type]
    proc.stdin.write("".join(json.dumps(r) + "\n" for r in REQUESTS))
    proc.stdin.flush()

    answers: dict[str, str] = {}
    ended: set[str] = set()
    watchdog = threading.Timer(timeout, proc.kill)  # si el daemon se cuelga, se corta
    watchdog.start()
    try:
        for line in proc.stdout:
            event = json.loads(line)
            kind, invoke_id, response = event.get("type"), event.get("invoke_id"), event.get("response") or {}
            if kind == "plugin_response":
                answers[invoke_id] = answers.get(invoke_id, "") + str((response.get("message") or {}).get("text", ""))
            elif kind == "error" and invoke_id:
                error = response.get("error", "")
                try:
                    answers[invoke_id] = json.loads(error).get("message", error)
                except ValueError:
                    answers[invoke_id] = error
            elif kind == "error":
                print(f"The plugin did not start: {response}", file=sys.stderr)
                break
            elif kind == "plugin_invoke_end":
                ended.add(invoke_id)
            if len(ended) == len(REQUESTS):
                break
    finally:
        watchdog.cancel()
        proc.kill()
        proc.wait()
        shutil.rmtree(work, ignore_errors=True)

    failed = False
    for invoke_id, expected in EXPECTED.items():
        got = answers.get(invoke_id, "(no answer)")
        ok = got.startswith(expected)
        failed |= not ok
        print(f"{'ok  ' if ok else 'FAIL'} {invoke_id}: {got}")
    if failed:
        print("".join(stderr[-40:]), file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
