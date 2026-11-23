# Product Analytics Copilot

Faça perguntas em **linguagem natural** sobre um produto SaaS e receba **resposta em
texto, gráfico, tabela, definição da métrica e o SQL executado**, sempre calculados
a partir de SQL parametrizado, somente leitura e auditável.

> "Qual a taxa de ativação?" → *A taxa de ativação em 7 dias após o signup é 50.5%:
> 6065 de 12000 usuários cadastrados no período ativaram.* + KPI + tabela + definição + SQL

**Stack:** FastAPI · Streamlit · DuckDB · Pydantic · Plotly · pytest

## Como funciona

```
Streamlit UI → FastAPI → IntentRouter → MetricRegistry → QueryEngine (DuckDB, read-only) → AskResponse
```

| Camada | Arquivo | Papel |
|---|---|---|
| IntentRouter | `app/core/router.py` | Mapeia a pergunta para uma métrica por sinônimos, com score e limiar. **Sem LLM.** |
| MetricRegistry | `app/core/registry.py` | Whitelist de `MetricSpec`, montados de `app/data/catalog.yml` + `app/data/sql/<métrica>/v1.sql` |
| QueryEngine | `app/core/engine.py` | Executa só os templates da registry, com binding de parâmetros, read-only, timeout e limite de linhas |
| Copilot | `app/core/copilot.py` | Orquestra tudo e monta a `AskResponse`; o texto vem de template preenchido com o resultado |
| Charts | `app/core/charts.py` | Figura Plotly (JSON) a partir das linhas do resultado |
| API | `app/api/main.py` | `POST /ask`, `GET /metrics`, `GET /health` |
| UI | `app/ui/streamlit_app.py` | Front que consome a API |
| Dados | `app/data/generate.py` | Gerador sintético com seed fixa (12.000 usuários, sem PII) |

### Métricas disponíveis

| Métrica | Definição resumida | Exemplos de pergunta |
|---|---|---|
| `activation_rate` | `activated` em até 7 dias após o signup ÷ signups | "qual a taxa de ativação?" |
| `onboarding_funnel` | usuários por passo do onboarding, % do topo e do passo anterior | "mostre o funil de onboarding" |
| `retention_d7` | atividade no **dia 7 exato** após o signup, janela `[D+7, D+8)` | "como está a retenção D7?" |
| `feature_adoption` | usuários que usaram a feature ÷ usuários ativos | "quais features são mais usadas?" |

Perguntas fora dessa lista (ex.: "qual a receita?") recebem uma resposta honesta,
"não sei", com a lista de métricas disponíveis. Perguntas que citam duas métricas
ao mesmo tempo também não são respondidas: o sistema pede uma por vez.

## Como rodar

Requer Python 3.11+.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**1. API** (gera `app/data/warehouse.duckdb` na primeira inicialização, em ~10s):

```bash
uvicorn app.api.main:app --port 8000
```

**2. UI** (em outro terminal):

```bash
streamlit run app/ui/streamlit_app.py
```

Abra http://localhost:8501.

**Direto pela API:**

```bash
curl -s localhost:8000/ask -H 'Content-Type: application/json' \
  -d '{"question": "Como está a retenção D7?"}'
```

**Resumo das métricas no terminal:**

```bash
python -m app.data.summary
```

### Configuração

| Variável | Default | Uso |
|---|---|---|
| `PAC_DB_PATH` | `app/data/warehouse.duckdb` | Arquivo DuckDB da API (gerado se não existir) |
| `PAC_CORS_ORIGINS` | `http://localhost:8501,http://127.0.0.1:8501` | Origens permitidas no CORS |
| `PAC_API_URL` | `http://localhost:8000` | Endereço da API usado pela UI |

## Contrato de resposta (`POST /ask`)

| campo | descrição |
|---|---|
| `metric` | métrica identificada (ou `null`) |
| `answer` | texto montado por template a partir do resultado do SQL |
| `value` | valor principal (ex.: taxa), vindo de uma coluna do resultado |
| `definition` | definição da métrica, da mesma fonte que o SQL |
| `sql` | SQL exatamente como executado (com comentário dos parâmetros vinculados) |
| `table` | linhas do resultado |
| `chart` | figura Plotly em JSON |
| `confidence` | score do roteamento (0–1) |
| `matched` | se a pergunta casou com uma métrica |

## Garantias de segurança e anti-alucinação

- Nenhum SQL é gerado por IA ou pelo usuário: só templates versionados da registry.
- Parâmetros sempre por binding do DuckDB; a pergunta nunca chega ao SQL.
- Conexão DuckDB read-only, com timeout e limite de linhas por consulta.
- `value`, `table` e `chart` vêm só do resultado do SQL, e `answer` é um template
  preenchido com esse resultado. Os testes verificam que todo número citado na
  resposta existe no resultado.
- Input validado por Pydantic (1–500 caracteres, sem campos extras), CORS restrito e
  erros internos que não expõem o schema.
- Dados 100% sintéticos, com seed fixa.

## Adicionando uma métrica

1. Crie `app/data/sql/<nome>/v1.sql`, usando só `$start`, `$end` e `$window_days` e
   só eventos do enum `EventType`.
2. Adicione a entrada em `app/data/catalog.yml`: definição (descrevendo exatamente
   o SQL), título, sinônimos, visualização (`kpi`, `funnel` ou `bar`), coluna de
   valor e template de resposta.
3. Inclua o nome em `EXPECTED` (`tests/test_registry.py`) e uma pergunta de exemplo
   em `QUESTIONS` (`tests/test_copilot.py`). Esses testes passam a validar a
   coerência da métrica e o contrato anti-alucinação dela.

O gráfico `kpi` serve para qualquer métrica de valor único. Os gráficos `funnel` e
`bar` esperam as colunas das métricas atuais (`step`/`users` e
`feature_name`/`users`/`active_users`); uma métrica com outro formato precisa de um
builder novo em `app/core/charts.py`.

## Desenvolvimento

```bash
pytest -q               # suíte completa
ruff check .            # lint
ruff format --check .   # formatação
```

Decisões de design: [`docs/architecture.md`](docs/architecture.md).
