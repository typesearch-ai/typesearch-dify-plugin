"""El .difypkg que arma el CLI oficial de Dify: sólo lo que el plugin necesita para correr.

Necesita el CLI (``dify`` en el PATH, o su ruta en ``DIFY_CLI``); sin él, se saltea. En CI se baja de las
releases de langgenius/dify-plugin-daemon.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from typesearch_plugin import VERSION

from .conftest import ROOT

CLI = os.environ.get("DIFY_CLI") or shutil.which("dify") or shutil.which("dify-plugin")

EXPECTED = {
    "LICENSE",
    "PRIVACY.md",
    "README.md",
    "_assets/icon-dark.svg",
    "_assets/icon.svg",
    "main.py",
    "manifest.yaml",
    "provider/typesearch.py",
    "provider/typesearch.yaml",
    "requirements.txt",
    *(f"tools/{name}.{ext}" for name in ("search_news", "get_contents", "find_similar", "check_coverage") for ext in ("py", "yaml")),
    *(f"typesearch_plugin/{name}.py" for name in ("__init__", "api", "output", "params", "run")),
}


@pytest.mark.skipif(not CLI, reason="set DIFY_CLI to the Dify plugin CLI (dify-plugin-daemon releases) to build the package")
def test_the_package_has_only_the_runtime_files(tmp_path: Path) -> None:
    out = tmp_path / f"typesearch-{VERSION}.difypkg"
    done = subprocess.run([str(CLI), "plugin", "package", str(ROOT), "-o", str(out)], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    with zipfile.ZipFile(out) as z:
        names = {n for n in z.namelist() if not n.endswith("/")}
    assert names == EXPECTED
    assert out.stat().st_size < 100_000
