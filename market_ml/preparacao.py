def adicionar_features(tabela):
    dados = tabela.copy()

    dados["retorno_1h"] = dados["fechamento"].pct_change(fill_method=None)

    media20 = dados["fechamento"].rolling(window=20, min_periods=20).mean()
    dados["distancia_media20"] = dados["fechamento"] / media20 - 1

    return dados

def adicionar_alvo(tabela):
    dados = tabela.copy()

    proximo_fechamento = dados["fechamento"].shift(-1)

    dados["alvo_alta"] = (
        proximo_fechamento > dados["fechamento"]
    ).astype("Int64")

    dados.loc[proximo_fechamento.isna(), "alvo_alta"] = None

    return dados
