import ccxt
import pandas as pd


COLUNAS_CANDLES = [
    "timestamp", "abertura", "maxima", "minima", "fechamento", "volume"
    ]
COLUNAS_MERCADOS = [
    "corretora", "par", "ativo", "cotacao", "tipo", "ativo_no_catalogo"
    ]


def listar_corretoras():
    """Lista os identificadores incluídos na versão instalada do CCXT.

    """
    return sorted(ccxt.exchanges)


def criar_corretora(id_corretora):
    """Cria o conector escolhido, sem fixar uma corretora
    
    """
    if id_corretora not in listar_corretoras():
        raise ValueError(f"Corretora desconhecida no CCXT: {id_corretora}")

    classe_corretora = getattr(ccxt, id_corretora)
    return classe_corretora({"enableRateLimit": True, "timeout": 15000})


def listar_mercados(corretora):
    """Consulta os mercados expostos pelo conector;


    """
    mercados = corretora.load_markets()
    registros = []

    for par, mercado in mercados.items():
        registros.append({
            "corretora": corretora.id,
            "par": par,
            "ativo": mercado.get("base"),
            "cotacao": mercado.get("quote"),
            "tipo": mercado.get("type"),
            "ativo_no_catalogo": mercado.get("active"),
        })

    return pd.DataFrame(registros, columns=COLUNAS_MERCADOS).sort_values("par")


def buscar_candles(corretora, par, intervalo="1h", quantidade=5, inicio_ms=None):
    """Busca um lote e devolve uma tabela com a identificação da fonte.

    """
    if not isinstance(quantidade, int) or isinstance(quantidade, bool) or quantidade <= 0:
        raise ValueError("A quantidade deve ser um número inteiro positivo.")
    if not corretora.has.get("fetchOHLCV"):
        raise ValueError(f"{corretora.id} não oferece coleta de candles pelo conector.")

    mercados = corretora.load_markets()
    if par not in mercados:
        raise ValueError(f"Par não encontrado em {corretora.id}: {par}")
    if mercados[par].get("active") is False:
        raise ValueError(f"Par marcado como inativo em {corretora.id}: {par}")
    if corretora.timeframes and intervalo not in corretora.timeframes:
        raise ValueError(f"Intervalo não disponível em {corretora.id}: {intervalo}")

    momento_coleta = pd.Timestamp.now(tz="UTC")
    candles = corretora.fetch_ohlcv(
        par, timeframe=intervalo, since=inicio_ms, limit=quantidade
    )
    tabela = pd.DataFrame(candles, columns=COLUNAS_CANDLES)
    tabela["timestamp"] = pd.to_datetime(tabela["timestamp"], unit="ms", utc=True)
    horario_fechamento = tabela["timestamp"] + pd.Timedelta(hours=1)
    tabela = tabela.loc[horario_fechamento <= momento_coleta].copy()
    tabela.insert(0, "intervalo", intervalo)
    tabela.insert(0, "par", par)
    tabela.insert(0, "corretora", corretora.id)
    return tabela

def buscar_historico(
    corretora, par, inicio_ms, fim_ms, intervalo="1h", quantidade=500,
    ao_receber_lote=None,
):
    """Reúne lotes de candles fechados dentro do período escolhido.

    """
    if intervalo != "1h":
        raise ValueError("Esta versão de buscar_historico aceita apenas 1h.")
    if inicio_ms is None or fim_ms is None or inicio_ms >= fim_ms:
        raise ValueError("Informe datas válidas, com início anterior ao fim.")

    lotes = []
    proximo_inicio = inicio_ms
    limite = pd.to_datetime(fim_ms, unit="ms", utc=True)
    duracao = pd.Timedelta(hours=1)

    while proximo_inicio < fim_ms:
        lote = buscar_candles(
            corretora, par, intervalo=intervalo,
            quantidade=quantidade, inicio_ms=proximo_inicio,
        )
        inicio_lote = pd.to_datetime(proximo_inicio, unit="ms", utc=True)
        lote = lote.loc[
            (lote["timestamp"] >= inicio_lote)
            & (lote["timestamp"] + duracao <= limite)
        ]

        if lote.empty:
            break

        if ao_receber_lote is not None:
            ao_receber_lote(lote)
        lotes.append(lote)
        ultimo_horario = lote["timestamp"].max()
        proximo_inicio = int((ultimo_horario + duracao).timestamp() * 1000)

    if not lotes:
        return pd.DataFrame(
            columns=["corretora", "par", "intervalo"] + COLUNAS_CANDLES
        )

    historico = pd.concat(lotes, ignore_index=True)
    historico = historico.drop_duplicates(subset=["timestamp"])
    return historico.sort_values("timestamp").reset_index(drop=True)
