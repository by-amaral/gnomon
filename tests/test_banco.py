"""Testes de persistência e retomada, sem depender da internet."""

from io import StringIO
import json
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ccxt
import pandas as pd

from market_ml.banco import (
    conectar, importar_csv, ler_candles, listar_experimentos, periodos_faltantes,
    salvar_candles, salvar_experimento, salvar_mercados,
)
from market_ml.execucao import atualizar_historico, main
from test_treinamento import criar_candles, INICIO, FIM
from market_ml.treinamento import treinar_avaliar


class TestBanco(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.caminho = Path(self.temporario.name) / "dados" / "teste.db"
        self.tabela = criar_candles()

    def ler(self, par="BTC/USDT"):
        return ler_candles("teste", par, INICIO, FIM, caminho=self.caminho)

    def test_importacao_repetida_upsert_e_separacao_de_mercados(self):
        arquivo = Path(self.temporario.name) / "antigo.csv"
        self.tabela.to_csv(arquivo, index=False)
        importar_csv(arquivo, self.caminho)
        importar_csv(arquivo, self.caminho)
        self.assertTrue(arquivo.exists())
        self.assertEqual(len(self.ler()), 744)
        self.assertTrue(self.ler()["timestamp"].is_monotonic_increasing)
        alterado = self.tabela.iloc[[0]].copy()
        alterado["volume"] = 42.0
        salvar_candles(alterado, self.caminho)
        self.assertEqual(self.ler().iloc[0]["volume"], 42.0)
        outro = self.tabela.copy()
        outro["par"] = "BTC/BRL"
        salvar_candles(outro, self.caminho)
        self.assertEqual(len(self.ler("BTC/BRL")), 744)
        outro["corretora"] = "outra"
        salvar_candles(outro, self.caminho)
        self.assertEqual(len(self.ler()), 744)
        with conectar(self.caminho) as conexao:
            self.assertEqual(conexao.execute("SELECT count(*) FROM candles").fetchone()[0], 2232)

    def test_limites_lacunas_e_candles_invalidos(self):
        salvar_candles(self.tabela.drop(index=[0, 100, 101, 743]), self.caminho)
        periodos = periodos_faltantes(self.ler(), INICIO, FIM)
        self.assertEqual(len(periodos), 3)
        self.assertEqual([int((fim - inicio).total_seconds() / 3600)
                          for inicio, fim in periodos], [1, 2, 1])
        trecho = ler_candles(
            "teste", "BTC/USDT", "2026-08-01T01:00Z", "2026-08-01T03:00Z",
            caminho=self.caminho,
        )
        self.assertEqual(len(trecho), 2)
        invalido = self.tabela.iloc[:2].copy()
        invalido.loc[1, "maxima"] = 0
        with self.assertRaises(ValueError):
            salvar_candles(invalido, self.caminho)
        self.assertEqual(len(self.ler()), 740)
        futuro = self.tabela.iloc[:1].copy()
        futuro["timestamp"] = pd.Timestamp.now(tz="UTC").floor("h")
        with self.assertRaisesRegex(ValueError, "aberto"):
            salvar_candles(futuro, self.caminho)

    def test_catalogo_e_metadados_preservados_na_importacao(self):
        catalogo = pd.DataFrame([{
            "corretora": "teste", "par": "BTC/USDT", "ativo": "BTC",
            "cotacao": "USDT", "tipo": "spot", "ativo_no_catalogo": True,
        }])
        salvar_mercados(catalogo, self.caminho)
        salvar_candles(self.tabela, self.caminho)
        with conectar(self.caminho) as conexao:
            self.assertEqual(conexao.execute("SELECT tipo FROM mercados").fetchone()[0], "spot")

    def test_cache_completo_nao_chama_api_nem_cria_csv(self):
        salvar_candles(self.tabela, self.caminho)
        corretora = SimpleNamespace(id="teste")
        with (
            patch("market_ml.execucao.CORRETORAS_ALVO", ["teste"]),
            patch("market_ml.execucao.PARES_ALVO", ["BTC/USDT"]),
            patch("market_ml.execucao.criar_corretora", return_value=corretora),
            patch("market_ml.historico.listar_mercados", side_effect=AssertionError("Não consultar API")),
            patch("market_ml.historico.buscar_historico", side_effect=AssertionError("Não baixar novamente")),
            patch("sys.stdout", new=StringIO()),
        ):
            self.assertEqual(main(self.caminho), 0)
        self.assertEqual(listar_experimentos(self.caminho)["id"].nunique(), 1)
        self.assertEqual(list(Path(self.temporario.name).rglob("*.csv")), [])

    def test_falha_de_rede_preserva_lote_e_retomada_busca_so_restante(self):
        tabela = self.tabela
        class Corretora:
            id = "teste"
            has = {"fetchOHLCV": True}
            timeframes = {"1h": "1h"}
            falhar = True
            chamadas = []

            def load_markets(self):
                return {"BTC/USDT": {"base": "BTC", "quote": "USDT", "type": "spot", "active": True}}

            def fetch_ohlcv(self, par, timeframe, since, limit):
                self.chamadas.append(since)
                if len(self.chamadas) == 2 and self.falhar:
                    raise ccxt.NetworkError("queda simulada")
                dados = tabela[tabela["timestamp"] >= pd.Timestamp(since, unit="ms", tz="UTC")].head(limit)
                return [
                    [int(linha.timestamp.value // 1_000_000), linha.abertura,
                     linha.maxima, linha.minima, linha.fechamento, linha.volume]
                    for linha in dados.itertuples()
                ]
        corretora = Corretora()
        with self.assertRaises(ccxt.NetworkError):
            atualizar_historico(corretora, "BTC/USDT", INICIO, FIM, self.caminho)
        self.assertEqual(len(self.ler()), 500)
        corretora.falhar = False
        final = atualizar_historico(corretora, "BTC/USDT", INICIO, FIM, self.caminho)
        self.assertEqual(len(final), 744)
        self.assertEqual(corretora.chamadas[-1], int(tabela.iloc[500]["timestamp"].value // 1_000_000))

    def test_experimentos_independentes_snapshot_e_rollback(self):
        resultado = treinar_avaliar(self.tabela, INICIO, FIM)
        primeiro = salvar_experimento(resultado, self.caminho)
        segundo = salvar_experimento(resultado, self.caminho)
        self.assertNotEqual(primeiro, segundo)
        modificado = self.tabela.copy()
        modificado["volume"] = 99
        salvar_candles(modificado, self.caminho)
        with conectar(self.caminho) as conexao:
            documento = conexao.execute("""
                SELECT conteudo_json FROM artefatos_experimento
                WHERE experimento_id=? AND nome='candles'
            """, (primeiro,)).fetchone()[0]
            self.assertEqual(json.loads(documento)["data"][0]["volume"], 10.0)
            # Simula falha de gravação depois do INSERT do experimento.
            conexao.execute("""
                CREATE TRIGGER falha_metricas BEFORE INSERT ON metricas
                BEGIN SELECT RAISE(ABORT, 'falha simulada'); END
            """)
        with self.assertRaises(sqlite3.IntegrityError):
            salvar_experimento(resultado, self.caminho)
        self.assertEqual(listar_experimentos(self.caminho)["id"].nunique(), 2)
        with conectar(self.caminho) as conexao:
            self.assertEqual(conexao.execute("SELECT count(*) FROM experimentos").fetchone()[0], 2)
            self.assertEqual(conexao.execute("SELECT count(*) FROM artefatos_experimento").fetchone()[0], 8)


if __name__ == "__main__":
    unittest.main()
