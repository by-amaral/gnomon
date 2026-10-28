# Registro de QA - coleta de candles

Execução local em 16/10/2026: `python -m pytest -q` retornou **15 passed,
1 xfailed**. Os testes usam uma corretora simulada, sem chamadas à API.
O teste `xfail` falha pelo comportamento descrito abaixo; ele não é uma correção.

## BUG-01 - Candle fechado de 5 minutos é descartado

- **Estado:** aberto; reproduzido em `tests/test_qa_coleta.py`.
- **Local:** `market_ml.coleta.buscar_candles`.
- **Pré-condição:** a corretora oferece o intervalo `5m`. Ela devolve um candle
  com timestamp de abertura `2026-08-01 00:00 UTC`. O relógio da coleta marca
  `2026-08-01 00:06 UTC`.
- **Passos:** chamar `buscar_candles(corretora, "BTC/USDT", intervalo="5m")`
  com a corretora simulada e esse candle; executar
  `python -m pytest -q tests/test_qa_coleta.py`.
- **Esperado:** o candle permanece, pois fechou às 00:05 UTC.
- **Obtido:** a tabela fica vazia. A função soma uma hora à abertura para
  decidir se o candle fechou, mesmo quando recebeu `intervalo="5m"`.
- **Impacto:** o método expõe outros intervalos oferecidos pelo conector, mas
  descarta candles já fechados desses intervalos. A coleta histórica completa
  declara suporte apenas a `1h`; este caso afeta a função de lote.
- **Possível correção:** derivar a duração do intervalo no filtro de fechamento
  e testar `5m` e `1h`; alternativamente, rejeitar explicitamente os intervalos
  não suportados em `buscar_candles`.

## Casos também verificados

| Caso | Resultado esperado | Resultado observado |
|---|---|---|
| Quantidade 0, negativa, booleana ou fracionária | Rejeitar antes de chamar a API | Passou |
| Par desconhecido | Erro claro e nenhuma consulta de candles | Passou |
| Candle de 1h ainda aberto | Não incluir na tabela | Passou |
| Lotes sobrepostos e candle fora do fim do período | Remover duplicata e respeitar limite | Passou |

O registro documenta **uma falha reproduzida**. Os casos que passaram não são
bugs e não foram contados como tal.
