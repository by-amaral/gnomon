<p align="center"><img src="docs/brand/gnomon-gravura.png" alt="Gravura de um relógio solar, símbolo de GNOMON" width="260"></p>

<h1 align="center">GNOMON</h1>

**Projeto experimental em desenvolvimento.**

GNOMON é uma plataforma em desenvolvimento para análise de mercados com dados e
Machine Learning. O nome vem do grego *gnṓmōn*, associado a observar e examinar;
também nomeia a parte do relógio solar que projeta a sombra.

A ideia é permitir buscar um ativo e encontrar seu histórico, dados de diferentes
corretoras e análises de modelos avaliados com rigor.

Essa é a direção do projeto, não uma lista de recursos prontos. Estamos longe
da versão final.

## O que existe hoje

- Coleta de cripto com CCXT e candles de uma hora.
- Histórico em SQLite, com validação e busca de trechos ausentes.
- Primeiro modelo de regressão logística, avaliado em períodos posteriores ao treino.
- Painel local de testes para escolher corretora, par e datas e avaliar o modelo.

O painel está propositalmente simples, sem gráficos. Ainda não há atualização
automática, previsões ao vivo, execução de ordens ou backtest financeiro.
As métricas atuais não demonstram rentabilidade.

## Executar

Na pasta do projeto, com Python e o ambiente virtual preparados:

```powershell
# Se ainda não existir um ambiente:
python -m venv venv

.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe painel.py
```

Abra [http://127.0.0.1:5000](http://127.0.0.1:5000).
Para encerrar, pressione `Ctrl+C` no terminal.
As datas são em UTC: início incluído e final excluído, ambos às 00h.

## Organização

- `market_ml/`: coleta, banco, preparação e treinamento.
- `market_ml/web/`: painel de testes.
- `tests/`: testes automatizados.
- `docs/`: explicações detalhadas.
- `dados/`: banco e arquivos locais, ignorados pelo Git.

Os iniciadores `main.py`, `painel.py`, `banco.py` e `treinamento.py`
continuam na raiz. Preserve `dados/market_ml.db` ao mover o projeto.

## Testes e documentação

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m pytest -q
```

[Uso do painel](docs/painel.md) ·
[Funcionamento e limitações](docs/funcionamento.md) ·
[Problemas conhecidos](docs/qa-bugs.md)

Licença [MIT](LICENSE).
