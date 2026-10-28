"use strict";

const el = (id) => document.getElementById(id);
let ocupado = false, catalogoFonte = null, consulta = null, treinado = false;
let versaoSelecao = 0;
const datas = ["inicio", "fim"];

function status(texto, tipo = "") {
  el("estado").textContent = texto;
  el("estado").className = `status ${tipo}`;
}
function controles() {
  for (const id of ["corretora", "catalogo", ...datas]) el(id).disabled = ocupado;
  el("par").disabled = ocupado || catalogoFonte !== el("corretora").value;
  el("carregar").disabled = ocupado || !el("par").value || el("par").disabled;
  el("treinar").disabled = ocupado || !consulta?.pode_treinar || treinado;
  document.querySelector("main").setAttribute("aria-busy", String(ocupado));
}
function limparResultado() {
  versaoSelecao += 1;
  consulta = null;
  treinado = false;
  el("historico").hidden = true;
  el("resultado").hidden = true;
  el("vazio").hidden = false;
  controles();
}
function mudouSelecao() {
  limparResultado();
  status("Seleção alterada. Carregue o histórico para analisar esse período e mercado.");
}
el("corretora").addEventListener("change", () => {
  catalogoFonte = null;
  el("par").replaceChildren(new Option("Carregue o catálogo primeiro", ""));
  el("catalogo-nota").textContent = "Carregue o catálogo da nova corretora.";
  mudouSelecao();
});
for (const id of ["par", ...datas]) el(id).addEventListener("change", mudouSelecao);
for (const id of datas) el(id).addEventListener("input", mudouSelecao);

async function enviar(caminho, dados) {
  const resposta = await fetch(caminho, {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify(dados),
  });
  const conteudo = await resposta.json();
  if (!resposta.ok) throw new Error(conteudo.erro || "Não foi possível concluir a operação.");
  return conteudo;
}
async function executar(mensagem, tarefa) {
  if (ocupado) return;
  ocupado = true;
  controles();
  status(mensagem, "busy");
  try { await tarefa(); }
  catch (erro) {
    status(erro instanceof TypeError
      ? "Não foi possível acessar o painel. Verifique se ele continua aberto no terminal."
      : erro.message, "error");
  } finally {
    if (!catalogoFonte) el("par").replaceChildren(new Option("Carregue o catálogo", ""));
    ocupado = false;
    controles();
  }
}
el("catalogo").addEventListener("click", () => executar("Consultando os mercados da corretora…", async () => {
  limparResultado();
  catalogoFonte = null;
  el("par").replaceChildren(new Option("Carregando…", ""));
  const fonte = el("corretora").value;
  const dados = await enviar("/api/catalogo", {corretora: fonte});
  catalogoFonte = dados.corretora;
  el("par").replaceChildren(...dados.pares.map((par) => new Option(par, par)));
  if (dados.pares.includes("BTC/USDT")) el("par").value = "BTC/USDT";
  el("catalogo-nota").textContent = `${dados.quantidade} pares spot. A disponibilidade histórica depende da fonte.`;
  status("Catálogo carregado. Escolha o par e as datas, depois carregue o histórico.");
}));
el("carregar").addEventListener("click", () => executar("Carregando histórico: consultando o banco e buscando os trechos ausentes…", async () => {
  limparResultado();
  const versao = versaoSelecao;
  const dados = await enviar("/api/historico", {
    corretora: el("corretora").value, par: el("par").value,
    inicio: el("inicio").value, fim: el("fim").value,
  });
  if (versao !== versaoSelecao) return;
  consulta = dados;
  await mostrarHistorico(dados);
  status(dados.aviso || (dados.quantidade ? "Histórico carregado e verificado." : dados.motivo_bloqueio),
    dados.aviso || !dados.quantidade ? "error" : "");
}));
function horario(iso) {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short", timeStyle: "short", timeZone: "UTC",
  }).format(new Date(iso));
}
function tabela(container, cabecalhos, linhas) {
  const table = document.createElement("table");
  const thead = table.createTHead(), tr = thead.insertRow();
  for (const titulo of cabecalhos) {
    const th = document.createElement("th");
    th.textContent = titulo; th.scope = "col"; tr.append(th);
  }
  const tbody = table.createTBody();
  for (const linha of linhas) {
    const row = tbody.insertRow();
    for (const valor of linha) row.insertCell().textContent = valor ?? "—";
  }
  el(container).replaceChildren(table);
}
async function mostrarHistorico(dados) {
  el("vazio").hidden = true;
  el("historico").hidden = false;
  el("mercado").textContent = dados.selecao.par;
  el("fonte").textContent = `${dados.selecao.corretora} · spot`;
  el("quantidade").textContent = dados.quantidade.toLocaleString("pt-BR");
  const esperados = (new Date(dados.selecao.fim) - new Date(dados.selecao.inicio)) / 3600000;
  el("cobertura").textContent = `${(100 * (esperados - dados.validacao.horarios_faltantes) / esperados).toLocaleString("pt-BR", {maximumFractionDigits: 1})}%`;
  el("qualidade-resumo").textContent = `${dados.validacao.horarios_faltantes} hora(s) ausente(s)`;
  el("periodo").textContent = `Solicitado: ${horario(dados.selecao.inicio)} até ${horario(dados.selecao.fim)} (excluído).
    Disponível: ${horario(dados.primeiro)} até ${horario(dados.ultimo)} UTC (aberturas).`;
  el("treino-motivo").textContent = dados.motivo_bloqueio || "Dados validados. O treinamento só começa ao clicar abaixo.";
  const nomes = {
    horarios_invalidos: "Horários inválidos", horarios_faltantes: "Horas ausentes",
    horarios_inesperados: "Horários inesperados", horarios_duplicados: "Horários duplicados",
    fora_de_ordem: "Série fora de ordem", valores_numericos_invalidos: "Números inválidos",
    candles_com_precos_incoerentes: "Preços incoerentes",
    candles_com_precos_nao_positivos: "Preços não positivos", volumes_negativos: "Volumes negativos",
  };
  const checks = document.createElement("div"); checks.className = "checks";
  for (const [chave, valor] of Object.entries(dados.validacao)) {
    const row = document.createElement("div"); row.className = `check ${valor ? "bad" : ""}`;
    const span = document.createElement("span"), b = document.createElement("b");
    span.textContent = nomes[chave] || chave; b.textContent = valor; row.append(span, b); checks.append(row);
  }
  el("validacao").replaceChildren(checks);
  el("lacunas").replaceChildren();
  if (dados.lacunas.length) {
    const p = document.createElement("p"); p.className = "small warning";
    p.textContent = `${dados.lacunas.length} trecho(s) sem dados. Não foram preenchidos artificialmente.`;
    el("lacunas").append(p);
    const ul = document.createElement("ul"); ul.className = "small muted";
    for (const falta of dados.lacunas.slice(0, 20)) {
      const li = document.createElement("li");
      li.textContent = `${horario(falta.inicio)} → ${horario(falta.fim)} UTC (final excluído)`; ul.append(li);
    }
    el("lacunas").append(ul);
    if (dados.lacunas.length > 20) {
      const extra = document.createElement("p"); extra.textContent = "Exibindo os primeiros 20 trechos.";
      el("lacunas").append(extra);
    }
  }
  el("qualidade").open = Object.values(dados.validacao).some(valor => valor > 0);
}

const percentual = (v) => v == null ? "—" : `${(v * 100).toLocaleString("pt-BR", {minimumFractionDigits: 2, maximumFractionDigits: 2})}%`;
el("treinar").addEventListener("click", () => executar("Treinando e avaliando em três etapas temporais…", async () => {
  const id = consulta.consulta_id, versao = versaoSelecao;
  const dados = await enviar("/api/treinar", {consulta_id: id});
  if (versao !== versaoSelecao || consulta?.consulta_id !== dados.consulta_id) return;
  treinado = true;
  el("resultado").hidden = false;
  el("experimento").textContent = `Experimento ${dados.experimento_id} · ${dados.exemplos} exemplos utilizáveis.
    Período: ${horario(dados.selecao.inicio)} → ${horario(dados.selecao.fim)} UTC (final excluído).`;
  tabela("metricas", ["Método", "Exemplos avaliados", "Acurácia", "Balanceada", "Log loss"],
    dados.metricas.map(r => [
      r.metodo === "regressao_logistica" ? "Regressão logística" : "Referência: classe mais frequente",
      r.exemplos_avaliados, percentual(r.acuracia), percentual(r.acuracia_balanceada), r.log_loss?.toLocaleString("pt-BR", {minimumFractionDigits: 4, maximumFractionDigits: 4}),
    ]));
  tabela("etapas", ["Etapa", "Treino", "Teste", "Primeira previsão avaliada (UTC)", "Última previsão avaliada (UTC)", "Acurácia", "Referência"],
    dados.etapas.map(r => [r.etapa, r.exemplos_treino, r.exemplos_teste,
      horario(r.primeira_previsao_teste), horario(r.ultima_previsao_teste),
      percentual(r.acuracia_modelo), percentual(r.acuracia_referencia)]));
  el("treino-motivo").textContent = "Experimento salvo. Para iniciar outra execução, carregue novamente o histórico.";
  status("Treinamento concluído. Resultados históricos salvos no banco.");
}));
controles();
