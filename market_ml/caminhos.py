"""Caminhos ancorados no projeto, sem depender da pasta aberta no terminal."""

from pathlib import Path

RAIZ_PROJETO = Path(__file__).resolve().parents[1]
PASTA_DADOS = RAIZ_PROJETO / "dados"
CAMINHO_BANCO = PASTA_DADOS / "market_ml.db"
