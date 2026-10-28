"""Persistência local em SQLite. Importar este módulo não cria arquivos."""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

import pandas as pd

from market_ml.caminhos import CAMINHO_BANCO
from market_ml.validacao import verificar_dados


COLUNAS = [
    "corretora", "par", "intervalo", "timestamp",
    "abertura", "maxima", "minima", "fechamento", "volume",
]
ESQUEMA = [
    """CREATE TABLE mercados (
        corretora TEXT NOT NULL, par TEXT NOT NULL,
        ativo TEXT, cotacao TEXT, tipo TEXT, ativo_no_catalogo INTEGER,
        atualizado_em TEXT NOT NULL,
        PRIMARY KEY (corretora, par)
    )""",
    """CREATE TABLE candles (
        corretora TEXT NOT NULL, par TEXT NOT NULL,
        intervalo TEXT NOT NULL CHECK (intervalo = '1h'),
        timestamp_ms INTEGER NOT NULL,
        abertura REAL NOT NULL CHECK (abertura > 0),
        maxima REAL NOT NULL, minima REAL NOT NULL,
        fechamento REAL NOT NULL CHECK (fechamento > 0),
        volume REAL NOT NULL CHECK (volume >= 0),
        atualizado_em TEXT NOT NULL,
        PRIMARY KEY (corretora, par, intervalo, timestamp_ms),
        CHECK (minima > 0 AND minima <= abertura AND minima <= fechamento),
        CHECK (maxima >= abertura AND maxima >= fechamento),
        FOREIGN KEY (corretora, par) REFERENCES mercados(corretora, par)
    )""",
    """CREATE TABLE experimentos (
        id TEXT PRIMARY KEY, criado_em TEXT NOT NULL,
        corretora TEXT NOT NULL, par TEXT NOT NULL, intervalo TEXT NOT NULL,
        configuracao_json TEXT NOT NULL
    )""",
    """CREATE TABLE metricas (
        experimento_id TEXT NOT NULL, metodo TEXT NOT NULL,
        exemplos_avaliados INTEGER NOT NULL,
        acuracia REAL, acuracia_balanceada REAL, log_loss REAL,
        PRIMARY KEY (experimento_id, metodo),
        FOREIGN KEY (experimento_id) REFERENCES experimentos(id)
    )""",
    """CREATE TABLE artefatos_experimento (
        experimento_id TEXT NOT NULL, nome TEXT NOT NULL, conteudo_json TEXT NOT NULL,
        PRIMARY KEY (experimento_id, nome),
        FOREIGN KEY (experimento_id) REFERENCES experimentos(id)
    )""",
]


def agora_utc():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def conectar(caminho=CAMINHO_BANCO):
    """Cria o esquema na primeira abertura; confirma ou desfaz cada operação."""
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conexao = sqlite3.connect(caminho, timeout=30)
    try:
        conexao.execute("PRAGMA foreign_keys = ON")
        versao = conexao.execute("PRAGMA user_version").fetchone()[0]
        if versao not in (0, 1):
            raise ValueError(f"Versão de banco não suportada: {versao}")
        if versao == 0:
            with conexao:
                conexao.execute("BEGIN IMMEDIATE")
                for comando in ESQUEMA:
                    conexao.execute(comando)
                conexao.execute("PRAGMA user_version = 1")
        with conexao:
            yield conexao
    finally:
        conexao.close()


def salvar_mercados(tabela, caminho=CAMINHO_BANCO):
    registros = []
    for linha in tabela.to_dict("records"):
        registros.append((
            linha["corretora"], linha["par"],
            *[None if pd.isna(linha.get(chave)) else linha[chave]
              for chave in ("ativo", "cotacao", "tipo", "ativo_no_catalogo")],
            agora_utc(),
        ))
    with conectar(caminho) as conexao:
        conexao.executemany("""
            INSERT INTO mercados VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(corretora, par) DO UPDATE SET
                ativo=excluded.ativo, cotacao=excluded.cotacao, tipo=excluded.tipo,
                ativo_no_catalogo=excluded.ativo_no_catalogo,
                atualizado_em=excluded.atualizado_em
        """, registros)


def salvar_candles(tabela, caminho=CAMINHO_BANCO):
    """Grava um lote validado; repetir a chave atualiza o candle, sem duplicá-lo."""
    faltantes = set(COLUNAS) - set(tabela.columns)
    if faltantes:
        raise ValueError(f"Colunas ausentes: {sorted(faltantes)}")
    if tabela.empty:
        return 0
    dados = tabela[COLUNAS].copy()
    dados["timestamp"] = pd.to_datetime(dados["timestamp"], utc=True)
    inicio = dados["timestamp"].min()
    fim = dados["timestamp"].max() + pd.Timedelta(hours=1)
    relatorio = verificar_dados(dados, inicio, fim)
    # Um lote pode ter lacunas. A cobertura completa será exigida antes do treino.
    relatorio.pop("horarios_faltantes")
    if any(relatorio.values()) or fim > pd.Timestamp.now(tz="UTC"):
        raise ValueError(f"Lote inválido ou com candle aberto: {relatorio}")
    dados[COLUNAS[4:]] = dados[COLUNAS[4:]].apply(pd.to_numeric)
    atualizado = agora_utc()
    registros = [
        (corretora, par, intervalo, int(timestamp.value // 1_000_000),
         float(abertura), float(maxima), float(minima), float(fechamento),
         float(volume), atualizado)
        for corretora, par, intervalo, timestamp, abertura, maxima, minima,
        fechamento, volume in dados.itertuples(index=False, name=None)
    ]
    with conectar(caminho) as conexao:
        # CSVs antigos não têm todo o catálogo: preservamos metadados desconhecidos.
        conexao.execute("""
            INSERT INTO mercados(corretora, par, atualizado_em) VALUES (?, ?, ?)
            ON CONFLICT(corretora, par) DO NOTHING
        """, (registros[0][0], registros[0][1], atualizado))
        conexao.executemany("""
            INSERT INTO candles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(corretora, par, intervalo, timestamp_ms) DO UPDATE SET
                abertura=excluded.abertura, maxima=excluded.maxima,
                minima=excluded.minima, fechamento=excluded.fechamento,
                volume=excluded.volume, atualizado_em=excluded.atualizado_em
        """, registros)
    return len(registros)


def limites_periodo(inicio, fim):
    inicio, fim = pd.to_datetime(inicio, utc=True), pd.to_datetime(fim, utc=True)
    if (pd.isna(inicio) or pd.isna(fim) or inicio >= fim
            or inicio != inicio.floor("h") or fim != fim.floor("h")):
        raise ValueError("Use início anterior ao fim, ambos em horas exatas.")
    return inicio, fim


def ler_candles(corretora, par, inicio, fim, intervalo="1h", caminho=CAMINHO_BANCO):
    """Consulta uma única série, ordenada; início inclusivo e fim exclusivo."""
    inicio, fim = limites_periodo(inicio, fim)
    if intervalo != "1h":
        raise ValueError("O banco deste piloto aceita apenas 1h.")
    with conectar(caminho) as conexao:
        tabela = pd.read_sql_query("""
            SELECT corretora, par, intervalo, timestamp_ms AS timestamp,
                   abertura, maxima, minima, fechamento, volume
            FROM candles
            WHERE corretora=? AND par=? AND intervalo=?
              AND timestamp_ms>=? AND timestamp_ms<?
            ORDER BY timestamp_ms
        """, conexao, params=(
            corretora, par, intervalo, int(inicio.value // 1_000_000),
            int(fim.value // 1_000_000),
        ))
    tabela["timestamp"] = pd.to_datetime(tabela["timestamp"], unit="ms", utc=True)
    return tabela


def periodos_faltantes(tabela, inicio, fim):
    """Agrupa horas ausentes em intervalos para buscar apenas o necessário."""
    inicio, fim = limites_periodo(inicio, fim)
    esperados = pd.date_range(inicio, fim, freq="h", inclusive="left")
    faltantes = esperados.difference(pd.DatetimeIndex(tabela["timestamp"]))
    periodos = []
    hora = pd.Timedelta(hours=1)
    for horario in faltantes:
        if periodos and periodos[-1][1] == horario:
            periodos[-1] = (periodos[-1][0], horario + hora)
        else:
            periodos.append((horario, horario + hora))
    return periodos


def importar_csv(arquivo, caminho=CAMINHO_BANCO):
    """Migração explícita e repetível; mantém o arquivo original."""
    return salvar_candles(pd.read_csv(arquivo), caminho)


def salvar_experimento(resultado, caminho=CAMINHO_BANCO):
    """Salva uma execução inteira numa transação, com cópias dos dados usados."""
    primeira = resultado["base"].iloc[0]
    identificador = uuid4().hex
    configuracao = json.dumps(resultado["configuracao"], ensure_ascii=False, allow_nan=False)
    artefatos = [
        (identificador, nome, resultado[nome].to_json(
            orient="table", date_format="iso", double_precision=15, index=False,
        ))
        for nome in ("candles", "base", "etapas", "previsoes")
    ]
    metricas = [
        (identificador, linha["metodo"], int(linha["exemplos_avaliados"]),
         *[None if pd.isna(linha[chave]) else float(linha[chave])
           for chave in ("acuracia", "acuracia_balanceada", "log_loss")])
        for linha in resultado["metricas"].to_dict("records")
    ]
    with conectar(caminho) as conexao:
        conexao.execute("INSERT INTO experimentos VALUES (?, ?, ?, ?, ?, ?)", (
            identificador, agora_utc(), primeira["corretora"], primeira["par"],
            primeira["intervalo"], configuracao,
        ))
        conexao.executemany("INSERT INTO artefatos_experimento VALUES (?, ?, ?)", artefatos)
        conexao.executemany("INSERT INTO metricas VALUES (?, ?, ?, ?, ?, ?)", metricas)
    return identificador


def listar_experimentos(caminho=CAMINHO_BANCO):
    with conectar(caminho) as conexao:
        return pd.read_sql_query("""
            SELECT e.id, e.criado_em, e.corretora, e.par, m.metodo,
                   m.exemplos_avaliados, m.acuracia, m.log_loss
            FROM experimentos e JOIN metricas m ON e.id=m.experimento_id
            ORDER BY e.criado_em, e.id, m.metodo
        """, conexao)


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", type=Path, default=CAMINHO_BANCO)
    parser.add_argument("--importar", type=Path, nargs="+", help="CSVs antigos de candles")
    args = parser.parse_args()
    try:
        for arquivo in args.importar or []:
            print(f"{arquivo.name}: {importar_csv(arquivo, args.banco)} candles processados.")
        print(f"Banco: {args.banco.resolve()}")
        print(listar_experimentos(args.banco).to_string(index=False))
    except (OSError, ValueError, sqlite3.Error) as erro:
        print(f"Falha no banco: {erro}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
