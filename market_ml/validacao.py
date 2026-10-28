import pandas as pd

def verificar_dados(tabela, data_inicio, data_fim):
    """Confere uma série de candles de 1h, de uma corretora e um par.

    """
    identificacao = tabela[["corretora", "par", "intervalo"]]
    if identificacao.isna().any().any():
        raise ValueError("Há candles sem identificação.")
    if not tabela.empty:
        if (identificacao.nunique() != 1).any():
            raise ValueError("Verifique uma corretora, par e intervalo por vez.")
        if not tabela["intervalo"].eq("1h").all():
            raise ValueError("Esta verificação aceita apenas candles de 1h.")

    inicio = pd.to_datetime(data_inicio, utc=True)
    fim = pd.to_datetime(data_fim, utc=True)
    if inicio >= fim or inicio != inicio.floor("h") or fim != fim.floor("h"):
        raise ValueError("Use início anterior ao fim, ambos em horas exatas.")

    esperados = pd.date_range(inicio, fim, freq="1h", inclusive="left")
    horarios = pd.to_datetime(tabela["timestamp"], utc=True, errors="coerce")
    recebidos = pd.DatetimeIndex(horarios.dropna())

    colunas = ["abertura", "maxima", "minima", "fechamento", "volume"]
    numeros = tabela[colunas].apply(pd.to_numeric, errors="coerce")
    numeros = numeros.replace([float("inf"), -float("inf")], float("nan"))

    incoerentes = (
        (numeros["maxima"] < numeros["minima"])
        | (numeros["abertura"] < numeros["minima"])
        | (numeros["abertura"] > numeros["maxima"])
        | (numeros["fechamento"] < numeros["minima"])
        | (numeros["fechamento"] > numeros["maxima"])
    )

    return {
        "horarios_invalidos": int(horarios.isna().sum()),
        "horarios_faltantes": len(esperados.difference(recebidos)),
        "horarios_inesperados": len(recebidos.difference(esperados)),
        "horarios_duplicados": int(recebidos.duplicated().sum()),
        "fora_de_ordem": int(not recebidos.is_monotonic_increasing),
        "valores_numericos_invalidos": int(numeros.isna().sum().sum()),
        "candles_com_precos_incoerentes": int(incoerentes.sum()),
        "candles_com_precos_nao_positivos": int(
            (numeros[colunas[:4]] <= 0).any(axis=1).sum()
        ),
        "volumes_negativos": int((numeros["volume"] < 0).sum()),
    }
