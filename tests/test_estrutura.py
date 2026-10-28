"""Regressões de caminhos e inicializadores após organizar o projeto."""

from pathlib import Path
import subprocess
import sys

from market_ml.caminhos import CAMINHO_BANCO, RAIZ_PROJETO
from market_ml.web.app import criar_app


def test_banco_e_recursos_independem_da_pasta_do_terminal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert CAMINHO_BANCO == RAIZ_PROJETO / "dados" / "market_ml.db"
    banco_teste = tmp_path / "teste.db"
    app = criar_app(banco_teste)
    cliente = app.test_client()
    assert cliente.get("/").status_code == 200
    assert cliente.get("/static/painel.css").status_code == 200
    assert cliente.get("/static/painel.js").status_code == 200
    assert not banco_teste.exists()


def test_iniciadores_aceitam_help_fora_da_raiz(tmp_path):
    for arquivo in ("painel.py", "treinamento.py", "banco.py"):
        processo = subprocess.run(
            [sys.executable, str(RAIZ_PROJETO / arquivo), "--help"],
            cwd=tmp_path, capture_output=True, text=True,
        )
        assert processo.returncode == 0, processo.stdout + processo.stderr
    assert not list(tmp_path.iterdir())
