# Funcionamento e limites do projeto

Detalhes da coleta, do banco e da avaliação temporal. Para instalar e executar,
consulte o [README](../README.md).

## Organização do banco

SQLite já faz parte do Python e não exige instalar um servidor. Um arquivo
contém tabelas que podem ser consultadas por corretora, par e período:

| Tabela | Conteúdo |
|---|---|
| `mercados` | Identificação e último catálogo observado; importações podem ter metadados desconhecidos |
| `candles` | OHLCV e timestamp UTC em milissegundos; uma linha por corretora/par/intervalo/horário |
| `experimentos` | ID, data da execução, mercado e configuração do treinamento |
| `metricas` | Medidas agregadas por experimento e método, consultáveis em SQL |
| `artefatos_experimento` | Cópias em JSON dos candles usados, base preparada, etapas e previsões |

A chave dos candles impede registros repetidos. Uma gravação explícita de um
candle existente atualiza seus valores; a coleta normal não revisita horários
já armazenados. Revisões posteriores de preços pela fonte exigem nova coleta
explícita. As cópias dos experimentos anteriores permanecem inalteradas.

Cada experimento é gravado numa transação: ou todos os seus registros são
confirmados, ou nenhum é. Guardamos período, features, parâmetros explícitos,
versões de pandas/scikit-learn e hashes do código de preparação, validação e
treinamento. Isso documenta a execução, mas não substitui guardar o código e
o ambiente se for necessário reproduzi-la integralmente.

Para consultar manualmente, por exemplo:

```sql
SELECT corretora, par, intervalo, COUNT(*) AS quantidade
FROM candles
GROUP BY corretora, par, intervalo;
```

O banco é local e ignorado pelo Git, assim como os CSVs antigos. Com o programa
fechado, copie `dados/market_ml.db` para fazer backup. Os resultados antigos em
`dados/legado/resultados/` são preservados, mas não são importados como novos experimentos.

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
zero impede o treinamento daquela série. Lotes válidos podem ser persistidos
mesmo quando há lacunas entre candles: a próxima execução tenta preencher essas
lacunas. Preços inválidos, timestamps duplicados no lote e candles abertos
impedem a gravação do lote inteiro.

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
no banco, identificados por um novo ID a cada execução:

| Registro no banco | Conteúdo |
|---|---|
| Artefato `candles` | Cópia do histórico fornecido ao treinamento |
| Artefato `base` | 724 exemplos utilizáveis, com features, alvo e horários de disponibilidade |
| Artefato `etapas` | Períodos de treino e avaliação, contagens e métricas por etapa |
| Artefato `previsoes` | 543 previsões fora do treino, probabilidades, referência e respostas reais |
| Tabela `metricas` | Comparação agregada entre regressão logística e referência |

Essas contagens pressupõem a amostra completa de agosto. Novas execuções
preservam os resultados anteriores. Os dados e resultados são
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
  ausentes. A validação impede treinar com séries incompletas para o período solicitado.
- A coleta usa o relógio local em UTC para filtrar candles abertos.
- As features pressupõem dados numéricos, ordenados e validados de uma única série.
- O banco e o fluxo incremental aceitam apenas `1h`. Não há coleta em paralelo,
  atualização automática em segundo plano ou revisão automática de candles antigos.
- Os artefatos JSON são cópias completas por experimento; podem consumir espaço
  com históricos muito maiores. Uma futura etapa pode usar artefatos compartilhados
  por versão de dataset. Esta estrutura prioriza a inspeção do piloto local.
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
5. **Expansão:** ampliar intervalos, ativos e fontes, organizar coleta concorrente
   quando necessário, comparar modelos e construir o site.

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

MIT — veja [LICENSE](../LICENSE).
