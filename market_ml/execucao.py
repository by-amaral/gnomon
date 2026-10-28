import sqlite3

import ccxt

from market_ml.coleta import criar_corretora, listar_corretoras
from market_ml.banco import CAMINHO_BANCO
from market_ml.historico import atualizar_historico
from market_ml.validacao import verificar_dados
from market_ml.preparacao import adicionar_features, adicionar_alvo
from market_ml.treinamento import mostrar_resultados, salvar_resultados, treinar_avaliar

CORRETORAS_ALVO = ["bybit"]
PARES_ALVO = ["BTC/BRL", "BTC/USDT"]
INTERVALO = "1h"
QUANTIDADE = 500
DATA_INICIO = "2026-08-01T00:00:00Z"
DATA_FIM = "2026-09-01T00:00:00Z"
PAR_TREINAMENTO = "BTC/USDT"


def main(caminho=CAMINHO_BANCO):
    ids_corretoras = listar_corretoras()
    print(f"Conectores conhecidos pelo CCXT instalado: {len(ids_corretoras)}")
    print(", ".join(ids_corretoras))
    print("Nesta execução, consultaremos:", ", ".join(CORRETORAS_ALVO))

    consultas_com_dados = 0
    treinamentos_concluidos = 0
    falha_treinamento = False
    for id_corretora in CORRETORAS_ALVO:
        try:
            corretora = criar_corretora(id_corretora)
        except (ccxt.BaseError, ValueError) as erro:
            print(f"Falha no catálogo de {id_corretora}: {erro}")
            continue

        for par in PARES_ALVO:
            try:
                tabela = atualizar_historico(
                    corretora, par, DATA_INICIO, DATA_FIM, caminho,
                    intervalo=INTERVALO, quantidade=QUANTIDADE,
                )

                relatorio = verificar_dados(tabela, DATA_INICIO, DATA_FIM)
                print(f"Verificação de {id_corretora} / {par}: {relatorio}")

                if any(relatorio.values()):
                    print("Histórico com problemas; treinamento bloqueado para esta série.")
                    continue

            except (ccxt.BaseError, ValueError, OSError, sqlite3.Error) as erro:
                print(f"Falha ao consultar {id_corretora} / {par}: {erro}")
                continue

            print(f"\n{id_corretora} / {par}: {len(tabela)} candles recebidos.")
            if tabela.empty:
                print("A consulta não retornou candles.")
            else:
                consultas_com_dados += 1
                print("Primeiro candle:", tabela["timestamp"].min())
                print("Último candle:", tabela["timestamp"].max())
                print(f"Histórico disponível em: {caminho}")

                dados = adicionar_features(tabela)
                dados = adicionar_alvo(dados)
                print(
                    dados[["timestamp", "fechamento", "alvo_alta"]]
                    .tail(5)
                    .to_string(index=False)
                )

                if par == PAR_TREINAMENTO:
                    try:
                        resultado = treinar_avaliar(tabela, DATA_INICIO, DATA_FIM)
                        identificador = salvar_resultados(resultado, caminho)
                    except (ValueError, OSError, sqlite3.Error) as erro:
                        falha_treinamento = True
                        print(f"Falha no treinamento de {id_corretora} / {par}: {erro}")
                    else:
                        treinamentos_concluidos += 1
                        mostrar_resultados(resultado)
                        print(f"Experimento salvo: {identificador}")

    if consultas_com_dados == 0:
        print("Nenhum histórico completo disponível; confira as mensagens acima.")
        return 1
    if treinamentos_concluidos == 0:
        print(f"Nenhum treinamento concluído para {PAR_TREINAMENTO}.")
        return 1
    return 1 if falha_treinamento else 0


if __name__ == "__main__":
    raise SystemExit(main())
