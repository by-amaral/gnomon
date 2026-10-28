"""Testes offline de preparação, separação temporal e avaliação do piloto."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler

from market_ml.preparacao import adicionar_alvo, adicionar_features
from market_ml.treinamento import FEATURES, preparar_base, salvar_resultados, treinar_avaliar
from market_ml.banco import conectar, listar_experimentos, salvar_candles


INICIO = "2026-08-01T00:00:00Z"
FIM = "2026-09-01T00:00:00Z"


def criar_candles():
    gerador = np.random.default_rng(42)
    fechamento = 100 * np.exp(np.cumsum(gerador.normal(0, 0.005, 744)))
    abertura = np.r_[fechamento[0], fechamento[:-1]]
    return pd.DataFrame({
        "corretora": "teste", "par": "BTC/USDT", "intervalo": "1h",
        "timestamp": pd.date_range(INICIO, periods=744, freq="h"),
        "abertura": abertura,
        "maxima": np.maximum(abertura, fechamento) + 1,
        "minima": np.minimum(abertura, fechamento) - 1,
        "fechamento": fechamento, "volume": 10.0,
    })


class TestPreparacao(unittest.TestCase):
    def test_alvo_alta_queda_empate_e_ultimo_desconhecido(self):
        tabela = pd.DataFrame({"fechamento": [100, 102, 101, 101]})
        resultado = adicionar_alvo(tabela)
        self.assertEqual(resultado["alvo_alta"].iloc[:3].tolist(), [1, 0, 0])
        self.assertTrue(pd.isna(resultado["alvo_alta"].iloc[-1]))
        self.assertNotIn("alvo_alta", tabela.columns)

    def test_features_e_ausencias_iniciais(self):
        tabela = pd.DataFrame({"fechamento": range(1, 22)})
        dados = adicionar_features(tabela)
        self.assertEqual(dados["retorno_1h"].isna().sum(), 1)
        self.assertEqual(dados["distancia_media20"].isna().sum(), 19)
        self.assertAlmostEqual(dados.loc[1, "retorno_1h"], 1.0)
        self.assertAlmostEqual(dados.loc[19, "distancia_media20"], 20 / 10.5 - 1)
        self.assertAlmostEqual(dados.loc[20, "distancia_media20"], 21 / 11.5 - 1)

    def test_base_remove_inicio_e_ultimo_alvo_sem_misturar_series(self):
        tabela = criar_candles()
        base = preparar_base(tabela, INICIO, FIM)
        self.assertEqual(len(base), 724)
        self.assertEqual(base.iloc[0]["timestamp"], tabela.iloc[19]["timestamp"])
        self.assertEqual(base.iloc[-1]["timestamp"], tabela.iloc[-2]["timestamp"])
        self.assertFalse(base[FEATURES + ["alvo_alta"]].isna().any().any())
        tabela.loc[0, "par"] = "ETH/USDT"
        with self.assertRaisesRegex(ValueError, "por vez"):
            preparar_base(tabela, INICIO, FIM)

    def test_historico_incompleto_e_precos_invalidos_sao_rejeitados(self):
        tabela = criar_candles()
        with self.assertRaisesRegex(ValueError, "Histórico inválido"):
            preparar_base(tabela.iloc[1:], INICIO, FIM)
        tabela.loc[0, "maxima"] = 0
        with self.assertRaisesRegex(ValueError, "Histórico inválido"):
            preparar_base(tabela, INICIO, FIM)


class TestWalkForward(unittest.TestCase):
    def test_treino_passado_gap_scaler_e_referencia(self):
        escaladores = []

        def criar_scaler():
            escalador = StandardScaler()
            escaladores.append(escalador)
            return escalador

        with patch("market_ml.treinamento.StandardScaler", side_effect=criar_scaler):
            resultado = treinar_avaliar(criar_candles(), INICIO, FIM)

        base = resultado["base"]
        previsoes = resultado["previsoes"]
        self.assertEqual(len(previsoes), 543)
        self.assertTrue(previsoes["timestamp"].is_unique)
        for etapa, (treino, teste) in enumerate(TimeSeriesSplit(n_splits=3, gap=1).split(base), 1):
            self.assertEqual(teste[0] - treino[-1], 2)
            self.assertLess(
                base.iloc[treino]["alvo_disponivel_em"].max(),
                base.iloc[teste]["momento_previsao"].min(),
            )
            np.testing.assert_allclose(
                escaladores[etapa - 1].mean_, base.iloc[treino][FEATURES].mean(),
            )
            self.assertEqual(escaladores[etapa - 1].n_samples_seen_, len(treino))
            saida = previsoes.loc[previsoes["etapa"] == etapa]
            np.testing.assert_allclose(
                saida["probabilidade_referencia"], base.iloc[treino]["alvo_alta"].mean(),
            )
            pd.testing.assert_series_equal(
                saida["timestamp"].reset_index(drop=True),
                base.iloc[teste]["timestamp"].reset_index(drop=True),
            )

    def test_mudar_futuro_nao_altera_primeira_avaliacao(self):
        tabela = criar_candles()
        original = treinar_avaliar(tabela, INICIO, FIM)["previsoes"]
        tabela.loc[700:, ["abertura", "maxima", "minima", "fechamento"]] *= 1.5
        alterado = treinar_avaliar(tabela, INICIO, FIM)["previsoes"]
        pd.testing.assert_frame_equal(
            original.loc[original["etapa"] == 1],
            alterado.loc[alterado["etapa"] == 1],
        )

    def test_treino_com_apenas_uma_classe_falha_claramente(self):
        tabela = criar_candles()
        tabela["fechamento"] = np.arange(100.0, 844.0)
        tabela["abertura"] = tabela["fechamento"]
        tabela["maxima"] = tabela["fechamento"] + 1
        tabela["minima"] = tabela["fechamento"] - 1
        with self.assertRaisesRegex(ValueError, "alta e queda/empate"):
            treinar_avaliar(tabela, INICIO, FIM)

    def test_resultados_e_execucao_por_csv(self):
        tabela = criar_candles()
        resultado = treinar_avaliar(tabela, INICIO, FIM)
        with tempfile.TemporaryDirectory() as pasta:
            banco = Path(pasta) / "teste.db"
            identificador = salvar_resultados(resultado, banco)
            self.assertEqual(set(listar_experimentos(banco)["id"]), {identificador})
            with conectar(banco) as conexao:
                self.assertEqual(conexao.execute(
                    "SELECT count(*) FROM artefatos_experimento"
                ).fetchone()[0], 4)
            arquivo = Path(pasta) / "candles.csv"
            tabela.to_csv(arquivo, index=False)
            # Compatibilidade de entrada: CSV antigo, resultados no banco temporário.
            processo = subprocess.run(
                [sys.executable, "-B", "treinamento.py", "--arquivo", str(arquivo),
                 "--banco", str(banco)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            )
            self.assertEqual(processo.returncode, 0, processo.stdout + processo.stderr)
            self.assertIn("724", processo.stdout)
            salvar_candles(tabela, banco)
            processo = subprocess.run(
                [sys.executable, "-B", "treinamento.py", "--corretora", "teste",
                 "--banco", str(banco)],
                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True,
            )
            self.assertEqual(processo.returncode, 0, processo.stdout + processo.stderr)
            self.assertEqual(listar_experimentos(banco)["id"].nunique(), 3)
            self.assertEqual(list(Path(pasta).glob("*.csv")), [arquivo])


if __name__ == "__main__":
    unittest.main()
