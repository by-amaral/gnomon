# market-ml-lab

Laboratório de aprendizado e pesquisa em Machine Learning aplicado a mercados.
O objetivo é construir uma plataforma com várias fontes, ativos e períodos,
modelos próprios e resultados avaliados com rigor.

O CCXT é o primeiro fornecedor de conectores. Fontes adicionais poderão ser
integradas para ampliar a cobertura de cripto, ações e commodities.
O projeto não faz recomendações de investimento nem executa operações.

## O que funciona agora

- Listar os identificadores de corretoras da versão instalada do CCXT.
- Criar um conector a partir do identificador escolhido.
- Consultar o catálogo de mercados de uma corretora pela API.
- Buscar históricos de candles de uma hora em lotes, com início e fim definidos.
- Devolver uma tabela com corretora, par, intervalo e horário UTC, além de OHLCV.
- Filtrar candles ainda abertos e limitar o histórico ao período solicitado.
- Reunir os lotes, remover horários repetidos e ordenar o histórico.
- Verificar identificação, cobertura temporal, duplicatas e coerência dos preços.
- Salvar um CSV de candles por corretora, par e intervalo após a validação.
- Calcular retorno de uma hora e distância relativa à média dos últimos 20 fechamentos.
- Criar o alvo de alta no próximo fechamento, preservando o último alvo desconhecido.
- Treinar regressão logística com três etapas de avaliação temporal walk-forward.
- Comparar o modelo com a previsão da classe mais frequente de cada treino.
- Salvar base preparada, previsões de avaliação e métricas em `resultados/`.
- Continuar a execução quando uma consulta falha, mostrando qual fonte falhou.

**Estágio atual: primeiro treinamento e avaliação temporal.** Os candles são
persistidos em CSV. Para o par de treinamento, uma base separada contém features
e alvo, e as previsões e métricas são gravadas para inspeção. Os modelos são
ajustados para a avaliação, mas ainda não são exportados para uso posterior.
Não há banco de dados, atualização incremental, backtest financeiro ou site.

## Arquivos e nomes

| Arquivo | Responsabilidade |
|---|---|
| `coleta.py` | Funções reutilizáveis; importar o arquivo não faz consultas |
| `validacao.py` | Verifica a qualidade de uma série de candles de uma hora |
| `preparacao.py` | Acrescenta features e alvo a uma cópia da tabela |
| `treinamento.py` | Prepara X/y, avalia o modelo e a referência e salva os resultados |
| `main.py` | Coleta, valida, salva candles e executa o treinamento do par escolhido |
| `tests/test_treinamento.py` | Testes offline de preparação e avaliação temporal (`unittest`) |
| `tests/test_qa_coleta.py` | Cenários de coleta com `pytest` e corretora simulada |
| `docs/qa-bugs.md` | Registro de falha reproduzida e casos de teste |
| `requirements.txt` | Dependências do ambiente |

| Nome | Significado |
|---|---|
| `id_corretora` | Texto que identifica o conector, como `kraken` |
| `corretora` | Objeto que sabe conversar com a API escolhida |
| `par` | Símbolo de um mercado, sem fixar o ativo ou a moeda no nome da variável |
| `intervalo` | Duração de cada candle, como `1h` |
| `quantidade` | Quantidade solicitada em uma chamada |
| `inicio_ms` | Início desejado em milissegundos UTC; omitido, usa o padrão da API |
| `fim_ms` | Limite final do histórico em milissegundos UTC |
| `mercados` | Catálogo de mercados, não o histórico de todos eles |
| `candles` | Lista recebida da API, dentro de `buscar_candles` |
| `tabela` | Dados organizados em um DataFrame do pandas |
| `lotes` | Tabelas reunidas por `buscar_historico` durante a paginação |
| `dados` | Cópia da tabela com as features acrescentadas |

`buscar_candles` devolve `tabela`. O chamador guarda esse retorno em sua própria
variável `tabela`. Os nomes são neutros e permanecem iguais para qualquer par.

## Como executar

Na pasta do projeto, usando PowerShell:

```powershell
# Apenas na preparação inicial do ambiente:
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt

# Para executar a coleta, a preparação e o primeiro treinamento:
.\venv\Scripts\python.exe main.py

# Para repetir o treinamento usando um CSV existente, sem consultar a API:
.\venv\Scripts\python.exe treinamento.py --arquivo bybit_BTC_USDT_1h.csv

# Para executar os testes offline:
.\venv\Scripts\python.exe -m unittest discover -s tests -v

# Para executar também os cenários de QA com pytest:
.\venv\Scripts\python.exe -m pip install pytest
.\venv\Scripts\python.exe -m pytest -q
```

Os cenários de QA usam uma corretora simulada: não consultam a internet nem
alteram CSVs reais. Um teste marcado `xfail` registra a falha aberta BUG-01;
o motivo e os passos para reproduzi-la estão em `docs/qa-bugs.md`.

As configurações ficam no início de `main.py`. A seleção atual é:

```python
CORRETORAS_ALVO = ["bybit"]
PARES_ALVO = ["BTC/BRL", "BTC/USDT"]
INTERVALO = "1h"
QUANTIDADE = 500
DATA_INICIO = "2026-08-01T00:00:00Z"
DATA_FIM = "2026-09-01T00:00:00Z"
PAR_TREINAMENTO = "BTC/USDT"
```

`QUANTIDADE` é o limite solicitado por lote, não o total de candles nem a
quantidade de arquivos. O período inclui 1º de agosto às 00:00 e termina antes
de 1º de setembro às 00:00 UTC. Com cobertura completa, são 744 candles por par.
BTC/BRL e BTC/USDT são mercados distintos do mesmo ativo; USDT não é USD.

O programa gera `bybit_BTC_BRL_1h.csv` e `bybit_BTC_USDT_1h.csv` após validar o
histórico coletado. Executar o programa substitui arquivos de mesmo nome na
pasta atual do terminal, sem acumular execuções. Eles contêm identificação,
timestamp e OHLCV, sem as features. Execute na pasta do projeto para mantê-los ali.
Os dois pares continuam sendo coletados, mas o piloto treina apenas BTC/USDT.
No comando de treinamento separado, use `--inicio` e `--fim` quando o CSV cobrir
outro período; os padrões são os mesmos de agosto acima. `--saida` permite
escolher outra pasta de resultados.

`listar_corretoras()` usa o catálogo local do CCXT. Estar nessa lista não garante
que a API esteja acessível ou que ofereça candles. `listar_mercados()` usa a
internet para consultar a API da corretora e mantém os tipos de mercado e o
estado de atividade fornecidos pela fonte. Estado desconhecido não é garantia
de atividade. Descobrir os mercados não significa baixar o histórico de todos.

Cada conector reutiliza seu controle de frequência de consultas. Quantidades,
intervalos, acesso e profundidade histórica dependem da corretora. Um lote pode
conter menos registros que o solicitado. O código não promete cobertura de 100%
dos mercados nem consulta todas as corretoras de uma vez.

## Validação e features

`verificar_dados` compara os horários recebidos com todas as horas esperadas no
período, incluindo suas extremidades. O relatório conta horários inválidos,
faltantes, inesperados e duplicados; ordem incorreta; números ausentes ou não
finitos; preços não positivos ou incoerentes; e volumes negativos. Cada chamada
verifica apenas uma corretora, par e intervalo. Qualquer contagem diferente de
zero impede a gravação daquela consulta; um CSV anterior permanece no disco.

A validação examina a tabela final: duplicatas removidas na paginação não
aparecem no relatório. Um resultado sem problemas indica consistência segundo
essas regras, não uma confirmação independente dos preços fornecidos pela API.

| Feature | Cálculo | Significado |
|---|---|---|
| `retorno_1h` | fechamento atual / anterior - 1 | Variação relativa na última hora |
| `distancia_media20` | fechamento atual / média dos 20 últimos fechamentos - 1 | Posição relativa à média recente |

Um retorno de `0.02` representa 2%. O primeiro retorno e as primeiras 19
distâncias à média ficam ausentes por falta de histórico anterior. Esses valores
não são preenchidos com zero. A média inclui o candle da própria linha: as
features pressupõem uma previsão feita depois que esse candle fecha.

`adicionar_alvo` compara o fechamento seguinte com o atual: alta recebe `1`,
queda ou empate recebe `0`. `shift(-1)` é usado somente para construir a
resposta histórica. O último alvo fica ausente; ele não é convertido em queda.

## Primeiro treinamento

O treinamento verifica uma série completa de 1h e usa somente estas entradas:

```python
FEATURES = ["retorno_1h", "distancia_media20"]
```

O alvo é `alvo_alta`. As primeiras 19 linhas sem média completa e a última linha
sem alvo são removidas da base do modelo. De 744 candles completos, restam 724
exemplos. O piloto exige pelo menos 100 exemplos utilizáveis apenas para evitar
execuções muito pequenas; esse mínimo não é evidência de suficiência estatística.

Usamos `TimeSeriesSplit(n_splits=3, gap=1)`, sem embaralhar. O treino cresce e a
avaliação avança no tempo. Cada etapa usa um novo modelo com parâmetros fixos,
sem busca de hiperparâmetros. Para a amostra de agosto:

| Etapa | Exemplos de treino | Separação | Exemplos de avaliação |
|---|---:|---:|---:|
| 1 | 180 | 1 hora | 181 |
| 2 | 361 | 1 hora | 181 |
| 3 | 542 | 1 hora | 181 |

O timestamp do candle indica sua abertura. A previsão acontece após uma hora,
e o alvo fica conhecido após duas horas. A separação de uma linha é conservadora:
exigimos que todos os alvos de treino estejam disponíveis antes da primeira
previsão avaliada. Blocos avaliados anteriormente podem integrar treinos futuros,
como em uma atualização ao longo do tempo; cada exemplo é avaliado uma única vez.

Um `StandardScaler` normaliza as features dentro de um pipeline com a regressão
logística. Ele aprende médias e escalas apenas no treino de cada etapa. A
referência usa `DummyClassifier(strategy="prior")`: prevê a classe mais frequente
e atribui probabilidades conforme a frequência de cada classe no treino.

O relatório mostra acurácia, acurácia balanceada e log loss para ambos os métodos.
Acurácia é taxa de acerto; a balanceada dá o mesmo peso ao acerto de cada classe;
log loss avalia as probabilidades e é melhor quando menor. Se uma avaliação tiver
apenas uma classe, a acurácia balanceada fica ausente. Se o treino tiver apenas
uma classe, a execução é interrompida com uma mensagem explicativa.

São 543 exemplos de avaliação ao todo na configuração acima. Resultados ficam
em `resultados/bybit_BTC_USDT_1h/`, separados dos candles originais:

| Arquivo gerado | Conteúdo |
|---|---|
| `base.csv` | 724 exemplos utilizáveis, com features, alvo e horários de disponibilidade |
| `etapas.csv` | Períodos de treino e avaliação, contagens e métricas por etapa |
| `previsoes.csv` | 543 previsões fora do treino, probabilidades, referência e respostas reais |
| `metricas.csv` | Comparação agregada entre regressão logística e referência |

Essas contagens pressupõem a amostra completa de agosto. Novas execuções
substituem os resultados do mesmo mercado. CSVs de candles e `resultados/` são
saídas locais ignoradas pelo Git. A avaliação é exploratória: ainda não há
simulação de ordens, custos ou slippage, nem um teste final separado para
confirmar futuras escolhas de features e modelos.

Na execução de verificação de 20/09/2026, com BTC/USDT da Bybit e o histórico
de agosto, foram avaliados 543 exemplos:

| Método | Acurácia | Acurácia balanceada | Log loss |
|---|---:|---:|---:|
| Regressão logística | 54,51% | 54,27% | 0,7434 |
| Classe mais frequente no treino | 49,17% | 49,63% | 0,6932 |

O modelo acertou mais direções nesse recorte, mas apresentou probabilidades
piores segundo log loss. Não foram ajustados parâmetros para melhorar esses
resultados. Esse piloto não comprova vantagem persistente nem rentabilidade.

## Limites atuais

- O fluxo de histórico e validação aceita apenas `1h`. O filtro de fechamento
  em `buscar_candles` também usa uma hora, mesmo que a função receba outro intervalo.
- Uma fonte pode devolver um histórico parcial; a paginação não cria dados
  ausentes. A validação impede salvar séries incompletas para o período solicitado.
- A coleta usa o relógio local em UTC para filtrar candles abertos.
- As features pressupõem dados numéricos, ordenados e validados de uma única série.
- Os CSVs são substituídos, sem retomada ou atualização incremental.
- Um mês é uma amostra para verificar o funcionamento; não demonstra capacidade
  preditiva ou desempenho de uma estratégia.

## Próximos passos

1. **Análise do piloto:** entender as métricas por período e a diferença em relação
   à referência, sem escolher um modelo só pelo melhor resultado observado.
2. **Histórico maior:** coletar mais meses, validar a cobertura e reservar um
   período final que não participe das decisões sobre features e modelos.
3. **Simulação:** definir quando seria possível executar cada decisão, incluir
   custos e slippage e registrar limitações do resultado.
4. **Comparações:** avaliar mudanças de features e modelos no desenvolvimento,
   mantendo a avaliação temporal e o teste final reservado.
5. **Expansão:** permitir atualização incremental e armazenamento em banco,
   ampliar intervalos, ativos e fontes, comparar modelos e construir o site.

O piloto não depende de coletar o mundo inteiro. A expansão deve respeitar a
cobertura das fontes. A quantidade de dados por si só não garante poder preditivo
nem significância estatística.

## Princípios

- Features usam informações disponíveis no instante da previsão.
- Rótulos representam resultados posteriores; cada treinamento utiliza apenas
  exemplos cujos rótulos já seriam conhecidos na sua data de corte.
- Pré-processamento e escolha do modelo respeitam os conjuntos de treino,
  validação e teste, sem aprender com dados reservados para avaliação final.
- Desempenho precisa ser verificado por mercado e período; sucesso em um ativo
  não demonstra automaticamente sucesso nos demais.
- A coleta continua separada dos modelos, permitindo acrescentar outras fontes.
- Deep Learning será avaliado quando houver motivo e comparação com baselines.

## Licença

MIT — veja [LICENSE](./LICENSE).
