"""Coordena ações explícitas do painel, sem depender de HTML ou Flask."""

from collections import OrderedDict
from datetime import date
import json
from threading import Lock
from uuid import uuid4

import ccxt
import pandas as pd

from market_ml.banco import CAMINHO_BANCO, ler_candles, limites_periodo, periodos_faltantes, salvar_mercados
from market_ml.coleta import criar_corretora, listar_mercados
from market_ml.historico import atualizar_historico
from market_ml.treinamento import preparar_base, salvar_resultados, treinar_avaliar
from market_ml.validacao import verificar_dados


def registros(tabela):
    """Converte datas para ISO e valores ausentes para null válido em JSON."""
    return json.loads(tabela.to_json(orient="records", date_format="iso", double_precision=15))


def validar_periodo(inicio, fim):
    try:
        inicio, fim = date.fromisoformat(inicio), date.fromisoformat(fim)
    except (TypeError, ValueError):
        raise ValueError("Preencha as duas datas no formato ano-mês-dia.") from None
    inicio, fim = limites_periodo(inicio, fim)
    if fim > pd.Timestamp.now(tz="UTC"):
        raise ValueError("A data final não pode estar no futuro. Use um período já encerrado.")
    if (fim - inicio) / pd.Timedelta(hours=1) > 100_000:
        raise ValueError("Este painel local aceita até 100.000 candles por consulta. Reduza o período.")
    return inicio, fim


class ServicoPainel:
    def __init__(self, caminho=CAMINHO_BANCO):
        self.caminho = caminho
        self.catalogos = {}
        self.consultas = OrderedDict()
        self.trava = Lock()  # Uma operação por vez, inclusive entre abas.

    def carregar_catalogo(self, id_corretora):
        corretora = criar_corretora(id_corretora)
        if not corretora.has.get("fetchOHLCV"):
            raise ValueError("Esse conector não oferece consulta de candles.")
        mercados = listar_mercados(corretora)
        if corretora.timeframes and "1h" not in corretora.timeframes:
            raise ValueError("Essa corretora não oferece candles de 1 hora pelo conector.")
        elegiveis = mercados.loc[
            mercados["tipo"].eq("spot")
            & ~mercados["ativo_no_catalogo"].eq(False).fillna(False)
        ]
        if elegiveis.empty:
            raise ValueError("Nenhum mercado spot elegível foi encontrado nessa fonte.")
        salvar_mercados(mercados, self.caminho)
        pares = elegiveis["par"].tolist()
        self.catalogos[id_corretora] = (corretora, set(pares))
        return {"corretora": id_corretora, "pares": pares, "quantidade": len(pares)}

    def carregar_historico(self, id_corretora, par, inicio, fim):
        inicio, fim = validar_periodo(inicio, fim)
        if id_corretora not in self.catalogos:
            raise ValueError("Carregue primeiro o catálogo da corretora selecionada.")
        corretora, pares = self.catalogos[id_corretora]
        if par not in pares:
            raise ValueError("Escolha um par do catálogo dessa corretora.")
        aviso = None
        try:
            tabela = atualizar_historico(corretora, par, inicio, fim, self.caminho)
        except (ccxt.BaseError, ValueError) as erro:
            tabela = ler_candles(id_corretora, par, inicio, fim, caminho=self.caminho)
            if tabela.empty:
                raise
            aviso = f"A coleta não foi concluída. Mostrando os dados salvos. {mensagem_erro(erro)}"
        relatorio = verificar_dados(tabela, inicio, fim)
        motivo = None
        if tabela.empty:
            motivo = "A fonte não retornou candles para esse período."
        elif any(relatorio.values()):
            motivo = "O histórico tem problemas de qualidade ou cobertura. O treino está bloqueado."
        else:
            try:
                preparar_base(tabela, inicio, fim)
            except ValueError as erro:
                motivo = str(erro)
        identificador = uuid4().hex
        selecao = {"corretora": id_corretora, "par": par, "inicio": inicio.isoformat(),
                   "fim": fim.isoformat(), "intervalo": "1h"}
        resposta = {
            "consulta_id": identificador, "selecao": selecao, "quantidade": len(tabela),
            "primeiro": None if tabela.empty else tabela["timestamp"].min().isoformat(),
            "ultimo": None if tabela.empty else tabela["timestamp"].max().isoformat(),
            "candles": registros(tabela), "validacao": relatorio,
            "lacunas": [{"inicio": a.isoformat(), "fim": b.isoformat()}
                        for a, b in periodos_faltantes(tabela, inicio, fim)],
            "pode_treinar": motivo is None, "motivo_bloqueio": motivo, "aviso": aviso,
        }
        self.consultas[identificador] = {
            "tabela": tabela.copy(), "selecao": selecao, "resposta": resposta, "treino": None,
        }
        while len(self.consultas) > 8:
            self.consultas.popitem(last=False)
        return resposta

    def treinar(self, identificador):
        consulta = self.consultas.get(identificador)
        if consulta is None:
            raise ValueError("Essa consulta expirou. Carregue o histórico novamente.")
        if consulta["treino"] is not None:
            return consulta["treino"]  # Repetição não cria outro experimento.
        if not consulta["resposta"]["pode_treinar"]:
            raise ValueError(consulta["resposta"]["motivo_bloqueio"])
        selecao = consulta["selecao"]
        resultado = treinar_avaliar(consulta["tabela"], selecao["inicio"], selecao["fim"])
        experimento = salvar_resultados(resultado, self.caminho)
        resposta = {
            "consulta_id": identificador, "experimento_id": experimento,
            "selecao": selecao, "metricas": registros(resultado["metricas"]),
            "etapas": registros(resultado["etapas"]), "exemplos": len(resultado["base"]),
        }
        consulta["treino"] = resposta
        return resposta


def mensagem_erro(erro):
    if isinstance(erro, ccxt.RateLimitExceeded):
        return "A corretora limitou as consultas. Aguarde um pouco e tente novamente."
    if isinstance(erro, ccxt.NetworkError):
        return "Não foi possível acessar a corretora. Confira a conexão ou tente outra fonte."
    if isinstance(erro, ccxt.BaseError):
        return "A corretora recusou a consulta ou não oferece esses dados pelo conector."
    if isinstance(erro, ValueError):
        return str(erro)
    return "Não foi possível acessar os dados locais. Confira o terminal para mais detalhes."
