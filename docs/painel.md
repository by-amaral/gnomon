# Uso do painel local

Na pasta do projeto:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe painel.py
```

Abra **http://127.0.0.1:5000** no navegador. Para encerrar, use `Ctrl+C` no
terminal que executa o painel. Caso a porta esteja ocupada:

```powershell
.\venv\Scripts\python.exe painel.py --porta 5001
```

O endereço passa a ser `http://127.0.0.1:5001`. Para um banco separado, use
`--banco caminho/alternativo.db`. O banco padrão continua em `dados/market_ml.db`.

1. Selecione a corretora e clique em **Carregar catálogo**. A página lista
   mercados spot não marcados como inativos; estado desconhecido não garante
   disponibilidade. Conectores sem candles ou sem intervalo `1h` são recusados.
2. Escolha o par, a data inicial e a final. Ambas representam **00:00 UTC**:
   o início está incluído e o final excluído. Para estudar agosto inteiro,
   use `01/08/2026` a `01/09/2026`.
3. Clique em **Carregar histórico**. O fluxo compartilhado consulta o SQLite,
   busca lacunas e salva lotes. A página mostra quantidade de candles, horários
   disponíveis, cobertura e verificações. Os gráficos foram retirados nesta fase de testes. Lacunas não são preenchidas artificialmente.
4. Se o histórico for válido e houver pelo menos 100 exemplos preparados,
   **Treinar e avaliar** fica disponível. O treinamento ainda pode recusar
   períodos cujo treino só contenha uma classe. As métricas e etapas aparecem
   junto ao ID do experimento salvo no SQLite.

O painel é destinado a testes e não exibe gráficos. As avaliações são históricas:
não representam previsões ao vivo ou rentabilidade. Os resultados de períodos
distintos não devem ser tratados como equivalentes.

Abrir a página ou alterar campos não faz consultas à corretora nem treina.
Mudar a seleção oculta os resultados anteriores. Durante uma operação, os
controles ficam bloqueados e uma mensagem indica a atividade. O servidor
aceita uma operação por vez, inclusive entre abas. Repetir o pedido de treino
da mesma consulta devolve o mesmo experimento; para executar novamente,
carregue o histórico outra vez.

Se a coleta falhar depois de salvar alguns lotes, os dados disponíveis ainda
podem ser inspecionados, com aviso. Séries incompletas não são treinadas.
Cada consulta está limitada a 100.000 candles para conter o uso de memória;
catálogo e profundidade histórica dependem da fonte. O catálogo exige conexão,
mesmo que já existam candles locais. As oito consultas mais recentes ficam
em memória; ao reiniciar o servidor, recarregue a seleção. Os candles e
experimentos já gravados permanecem no banco.

A implementação usa **Flask** para a página e as ações HTTP, HTML/CSS/JavaScript
sem etapa de compilação para a interface. Não carrega biblioteca de gráficos.
O servidor inicia somente em `127.0.0.1`, com depuração desligada; é destinado
ao uso local em um único processo, não à hospedagem pública.

O código da interface fica em `market_ml/web/`. As seções detalhadas de validação e resultados começam recolhidas para
manter a tela simples. Veja a visão geral no [README](../README.md).
