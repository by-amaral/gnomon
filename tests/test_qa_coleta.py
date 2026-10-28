"""Cenários de qualidade da coleta, sem acesso à API da corretora."""

import pandas as pd
import pytest

from market_ml.coleta import buscar_candles, buscar_historico


HORA_MS = 60 * 60 * 1000
BASE_MS = int(pd.Timestamp("2026-08-01T00:00:00Z").timestamp() * 1000)


class CorretoraFalsa:
    id = "simulada"
    has = {"fetchOHLCV": True}
    timeframes = {"1h": "1h", "5m": "5m"}

    def __init__(self, lotes):
        self.lotes = lotes
        self.chamadas = []

    def load_markets(self):
        return {"BTC/USDT": {"active": True}}

    def fetch_ohlcv(self, par, timeframe, since, limit):
        self.chamadas.append((par, timeframe, since, limit))
        return self.lotes.pop(0)


def candle(horario):
    return [horario, 100, 102, 99, 101, 10]


@pytest.mark.parametrize("quantidade", [0, -1, True, 1.5])
def test_quantidade_invalida_e_rejeitada_antes_da_api(quantidade):
    corretora = CorretoraFalsa([])
    with pytest.raises(ValueError, match="inteiro positivo"):
        buscar_candles(corretora, "BTC/USDT", quantidade=quantidade)
    assert corretora.chamadas == []


def test_par_desconhecido_nao_consulta_candles():
    corretora = CorretoraFalsa([])
    with pytest.raises(ValueError, match="Par não encontrado"):
        buscar_candles(corretora, "ETH/USDT")
    assert corretora.chamadas == []


def test_candle_de_uma_hora_ainda_aberto_e_descartado(monkeypatch):
    monkeypatch.setattr(pd.Timestamp, "now", lambda **_: pd.Timestamp("2026-08-01T01:30:00Z"))
    corretora = CorretoraFalsa([[candle(BASE_MS), candle(BASE_MS + HORA_MS)]])
    resultado = buscar_candles(corretora, "BTC/USDT")
    assert resultado["timestamp"].tolist() == [pd.Timestamp(BASE_MS, unit="ms", tz="UTC")]


def test_paginacao_remove_sobreposicao_e_limita_periodo(monkeypatch):
    monkeypatch.setattr(pd.Timestamp, "now", lambda **_: pd.Timestamp("2026-08-03T00:00:00Z"))
    corretora = CorretoraFalsa([
        [candle(BASE_MS), candle(BASE_MS + HORA_MS)],
        [candle(BASE_MS + HORA_MS), candle(BASE_MS + 2 * HORA_MS), candle(BASE_MS + 3 * HORA_MS)],
    ])
    resultado = buscar_historico(corretora, "BTC/USDT", BASE_MS, BASE_MS + 3 * HORA_MS, quantidade=3)
    assert resultado["timestamp"].tolist() == [
        pd.Timestamp(BASE_MS + h, unit="ms", tz="UTC") for h in (0, HORA_MS, 2 * HORA_MS)
    ]
    assert [chamada[2] for chamada in corretora.chamadas] == [BASE_MS, BASE_MS + 2 * HORA_MS]


@pytest.mark.xfail(strict=True, reason="BUG-01: 5m usa fechamento fixo de 1h")
def test_candle_de_cinco_minutos_fechado_deve_ser_mantido(monkeypatch):
    monkeypatch.setattr(pd.Timestamp, "now", lambda **_: pd.Timestamp("2026-08-01T00:06:00Z"))
    corretora = CorretoraFalsa([[candle(BASE_MS)]])
    resultado = buscar_candles(corretora, "BTC/USDT", intervalo="5m")
    assert len(resultado) == 1
