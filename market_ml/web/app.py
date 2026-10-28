"""Página local de análise. Execute: python painel.py"""

import argparse
from functools import wraps
from pathlib import Path
import sqlite3
from urllib.parse import urlsplit

import ccxt
from flask import Flask, jsonify, render_template, request

from market_ml.banco import CAMINHO_BANCO
from market_ml.coleta import listar_corretoras
from market_ml.web.servicos import ServicoPainel, mensagem_erro


def criar_app(caminho=CAMINHO_BANCO):
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=8192, TRUSTED_HOSTS=["127.0.0.1", "localhost"])
    servico = ServicoPainel(caminho)
    app.extensions["painel"] = servico

    @app.get("/")
    def inicio():
        return render_template("painel.html", corretoras=listar_corretoras())

    def operacao(funcao):
        @wraps(funcao)
        def executar():
            origem = request.headers.get("Origin")
            if origem and urlsplit(origem).netloc != request.host:
                return jsonify(erro="Use o painel no endereço local."), 403
            dados = request.get_json(silent=True)
            if not isinstance(dados, dict):
                return jsonify(erro="Envie uma seleção válida."), 400
            if not servico.trava.acquire(blocking=False):
                return jsonify(erro="Há uma operação em andamento. Aguarde a conclusão."), 409
            try:
                return jsonify(funcao(dados))
            except (ccxt.BaseError, ValueError) as erro:
                return jsonify(erro=mensagem_erro(erro)), 400
            except (OSError, sqlite3.Error) as erro:
                app.logger.exception("Erro ao acessar dados locais")
                return jsonify(erro=mensagem_erro(erro)), 500
            finally:
                servico.trava.release()
        return executar

    def texto(dados, chave):
        valor = dados.get(chave)
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"Preencha o campo {chave}.")
        return valor.strip()

    @app.post("/api/catalogo")
    @operacao
    def catalogo(dados):
        return servico.carregar_catalogo(texto(dados, "corretora"))

    @app.post("/api/historico")
    @operacao
    def historico(dados):
        return servico.carregar_historico(
            *(texto(dados, chave) for chave in ("corretora", "par", "inicio", "fim"))
        )

    @app.post("/api/treinar")
    @operacao
    def treinar(dados):
        return servico.treinar(texto(dados, "consulta_id"))

    return app


def main():
    """Inicia o servidor local; também usado pelo iniciador da raiz."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", type=Path, default=CAMINHO_BANCO)
    parser.add_argument("--porta", type=int, default=5000)
    args = parser.parse_args()
    criar_app(args.banco).run(host="127.0.0.1", port=args.porta, debug=False)
