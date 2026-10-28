"""Integração HTTP com SQLite temporário e corretoras simuladas."""

from pathlib import Path
from unittest.mock import patch

import ccxt
import pandas as pd
import pytest

from market_ml.banco import conectar, salvar_candles
from market_ml.web.app import criar_app
from market_ml.web.servicos import validar_periodo
from test_treinamento import criar_candles


class CorretoraSimulada:
    id = "teste"
    has = {"fetchOHLCV": True}
    timeframes = {"1h": "1h"}

    def load_markets(self):
        return {
            "BTC/USDT": {"base": "BTC", "quote": "USDT", "type": "spot", "active": True},
            "ETH/USDT": {"base": "ETH", "quote": "USDT", "type": "spot", "active": None},
            "VELHO/USDT": {"type": "spot", "active": False},
            "BTC/USDT:USDT": {"type": "swap", "active": True},
        }


@pytest.fixture
def ambiente(tmp_path):
    caminho = tmp_path / "painel.db"
    app = criar_app(caminho)
    app.config["TESTING"] = True
    return app, app.test_client(), caminho


def catalogo(cliente):
    with patch("market_ml.web.servicos.criar_corretora", return_value=CorretoraSimulada()):
        return cliente.post("/api/catalogo", json={"corretora": "teste"})


def historico(cliente, **alteracoes):
    selecao = {"corretora": "teste", "par": "BTC/USDT",
               "inicio": "2026-08-01", "fim": "2026-09-01"}
    selecao.update(alteracoes)
    return cliente.post("/api/historico", json=selecao)


def test_abrir_pagina_nao_acessa_api_banco_ou_treina(ambiente):
    _, cliente, caminho = ambiente
    with patch("market_ml.web.servicos.criar_corretora", side_effect=AssertionError("API")):
        resposta = cliente.get("/")
        assert resposta.status_code == 200
        assert "Carregar catálogo" in resposta.text
        assert cliente.get("/static/painel.js").status_code == 200
        assert "plotly" not in resposta.text.lower()
        assert cliente.get("/plotly.js").status_code == 404
    assert not caminho.exists()


def test_catalogo_filtra_inativos_derivativos_e_vincula_par(ambiente):
    _, cliente, _ = ambiente
    resposta = catalogo(cliente)
    assert resposta.json["pares"] == ["BTC/USDT", "ETH/USDT"]
    assert historico(cliente, par="BTC/USDT:USDT").status_code == 400
    assert historico(cliente, corretora="outra").status_code == 400


@pytest.mark.parametrize("capacidade,intervalos", [(False, {"1h": "1h"}), (True, {"5m": "5m"})])
def test_catalogo_sem_suporte(ambiente, capacidade, intervalos):
    _, cliente, _ = ambiente
    corretora = CorretoraSimulada()
    corretora.has = {"fetchOHLCV": capacidade}
    corretora.timeframes = intervalos
    with patch("market_ml.web.servicos.criar_corretora", return_value=corretora):
        assert cliente.post("/api/catalogo", json={"corretora": "teste"}).status_code == 400


@pytest.mark.parametrize("inicio,fim", [
    ("", "2026-09-01"), ("2026-09-01", "2026-08-01"),
    ("2026-08-01", "2026-08-01"), ("2026-08-01", "2999-01-01"),
    ("2026-02-30", "2026-09-01"),
])
def test_periodo_invalido_nao_coleta(ambiente, inicio, fim):
    _, cliente, _ = ambiente
    with patch("market_ml.web.servicos.atualizar_historico", side_effect=AssertionError("coleta")):
        assert historico(cliente, inicio=inicio, fim=fim).status_code == 400


def test_periodo_normalizado_em_utc():
    inicio, fim = validar_periodo("2026-08-01", "2026-09-01")
    assert inicio == pd.Timestamp("2026-08-01T00:00:00Z")
    assert (fim - inicio) / pd.Timedelta(hours=1) == 744


def test_cache_treino_explicito_e_pedido_repetido(ambiente):
    _, cliente, caminho = ambiente
    salvar_candles(criar_candles(), caminho)
    catalogo(cliente)
    with patch("market_ml.historico.buscar_historico", side_effect=AssertionError("redownload")):
        resposta = historico(cliente)
    assert resposta.status_code == 200
    dados = resposta.json
    assert dados["pode_treinar"] and dados["quantidade"] == 744
    assert dados["ultimo"] == "2026-08-31T23:00:00+00:00"
    with conectar(caminho) as conexao:
        assert conexao.execute("SELECT count(*) FROM experimentos").fetchone()[0] == 0
    treino = cliente.post("/api/treinar", json={"consulta_id": dados["consulta_id"]})
    assert treino.status_code == 200
    assert treino.json["exemplos"] == 724
    assert len(treino.json["metricas"]) == 2
    assert treino.json["metricas"][0]["exemplos_avaliados"] == 543
    repetido = cliente.post("/api/treinar", json={"consulta_id": dados["consulta_id"]})
    assert repetido.json["experimento_id"] == treino.json["experimento_id"]
    with conectar(caminho) as conexao:
        assert conexao.execute("SELECT count(*) FROM experimentos").fetchone()[0] == 1
    assert not list(caminho.parent.glob("*.csv"))


def test_lacunas_e_falha_parcial_bloqueiam_treino(ambiente):
    _, cliente, caminho = ambiente
    salvar_candles(criar_candles().drop(index=[10, 11]), caminho)
    catalogo(cliente)
    with patch("market_ml.web.servicos.atualizar_historico", side_effect=ccxt.NetworkError("offline")):
        dados = historico(cliente).json
    assert dados["quantidade"] == 742 and not dados["pode_treinar"]
    assert dados["validacao"]["horarios_faltantes"] == 2
    assert len(dados["lacunas"]) == 1 and dados["aviso"]
    assert cliente.post("/api/treinar", json={"consulta_id": dados["consulta_id"]}).status_code == 400


def test_poucos_dados_e_ausencia_total(ambiente):
    _, cliente, caminho = ambiente
    salvar_candles(criar_candles().iloc[:24], caminho)
    catalogo(cliente)
    dados = historico(cliente, fim="2026-08-02").json
    assert not dados["pode_treinar"] and "100" in dados["motivo_bloqueio"]
    with patch("market_ml.web.servicos.atualizar_historico", return_value=criar_candles().iloc[:0]):
        dados = historico(cliente).json
    assert dados["quantidade"] == 0 and not dados["pode_treinar"]


def test_operacao_concorrente_e_consulta_expirada(ambiente):
    app, cliente, _ = ambiente
    with app.extensions["painel"].trava:
        assert cliente.post("/api/catalogo", json={"corretora": "bybit"}).status_code == 409
    assert cliente.post("/api/treinar", json={"consulta_id": "inexistente"}).status_code == 400


def test_erros_de_rede_e_requisicoes_invalidas(ambiente):
    _, cliente, _ = ambiente
    with patch("market_ml.web.servicos.criar_corretora", side_effect=ccxt.NetworkError("endereco interno")):
        resposta = cliente.post("/api/catalogo", json={"corretora": "bybit"})
    assert resposta.status_code == 400
    assert "conexão" in resposta.json["erro"] and "endereco interno" not in resposta.text
    assert cliente.post("/api/catalogo", json=[]).status_code == 400
    assert cliente.post("/api/catalogo", json={"corretora": 3}).status_code == 400
    assert cliente.post("/api/catalogo", json={"corretora": "bybit"},
                        headers={"Origin": "https://outro-site.example"}).status_code == 403


def test_consultas_diferentes_mantem_seus_proprios_dados(ambiente):
    app, cliente, caminho = ambiente
    btc = criar_candles()
    eth = btc.assign(par="ETH/USDT")
    salvar_candles(btc, caminho)
    salvar_candles(eth, caminho)
    catalogo(cliente)
    primeira = historico(cliente).json
    segunda = historico(cliente, par="ETH/USDT").json
    assert primeira["consulta_id"] != segunda["consulta_id"]
    assert app.extensions["painel"].consultas[primeira["consulta_id"]]["selecao"]["par"] == "BTC/USDT"
    assert segunda["selecao"]["par"] == "ETH/USDT"
