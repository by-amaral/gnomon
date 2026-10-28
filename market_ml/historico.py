"""Fluxo compartilhado pelo terminal e pelo painel."""

from market_ml.banco import CAMINHO_BANCO, ler_candles, periodos_faltantes, salvar_candles, salvar_mercados
from market_ml.coleta import buscar_historico, listar_mercados


def atualizar_historico(corretora, par, inicio, fim, caminho=CAMINHO_BANCO,
                       intervalo="1h", quantidade=500):
    """Reutiliza o banco e persiste cada lote antes de buscar o seguinte."""
    tabela = ler_candles(corretora.id, par, inicio, fim, intervalo, caminho)
    periodos = periodos_faltantes(tabela, inicio, fim)
    if not periodos:
        print(f"{corretora.id} / {par}: histórico completo no banco; sem consulta à API.")
        return tabela
    salvar_mercados(listar_mercados(corretora), caminho)
    print(f"{corretora.id} / {par}: buscando {len(periodos)} trecho(s) ausente(s).")
    for inicio_trecho, fim_trecho in periodos:
        buscar_historico(
            corretora, par,
            inicio_ms=int(inicio_trecho.value // 1_000_000),
            fim_ms=int(fim_trecho.value // 1_000_000),
            intervalo=intervalo, quantidade=quantidade,
            ao_receber_lote=lambda lote: salvar_candles(lote, caminho),
        )
    return ler_candles(corretora.id, par, inicio, fim, intervalo, caminho)
