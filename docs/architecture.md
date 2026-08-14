# Product Analytics Copilot — Arquitetura

> **Status:** decisões de arquitetura (fase de design). Nenhum código de aplicação
> foi implementado ainda. Este documento é a fonte de verdade das decisões.

O **Product Analytics Copilot** recebe perguntas em linguagem natural sobre um
produto SaaS e devolve, para cada pergunta: **resposta em texto, gráfico, tabela,
definição da métrica e o SQL executado**.

**Stack:** FastAPI · Streamlit · DuckDB · Pydantic · Plotly · pytest.

## Decisões-chave

| Decisão | Escolha | Motivo |
|---|---|---|
| Interpretação da linguagem natural | **Roteador determinístico** (whitelist de métricas + matching por keywords/sinônimos) — sem LLM | Zero SQL gerado por IA, zero números inventados. História anti-alucinação forte e 100% auditável. |
| Fonte de dados | **Gerador sintético seedado** (seed fixo, reprodutível, sem PII) | Reprodutibilidade, testes determinísticos, ideal para portfólio. |

---

## 1. Plano de implementação

Fluxo de uma pergunta:

```
pergunta NL → IntentRouter → MetricSpec (whitelist) → SQL parametrizado
            → DuckDB → resultado → resposta + gráfico Plotly + tabela + definição + SQL
```

Camadas:

- **Ingestão** — gerador sintético popula as tabelas DuckDB (`events`, `users`).
- **Semântica** — `MetricRegistry`: cada métrica é um objeto Pydantic com nome,
  sinônimos, definição textual, template SQL parametrizado e tipo de visualização.
- **Roteamento** — `IntentRouter` mapeia o texto para um `MetricSpec` por
  keywords/sinônimos, com score e limiar. Abaixo do limiar → resposta honesta
  ("não entendi; estas são as métricas disponíveis").
- **Execução** — `QueryEngine` roda o SQL **read-only** contra o DuckDB, com
  parâmetros via binding (nunca concatenação de strings).
- **Apresentação** — FastAPI expõe `/ask`; Streamlit consome e renderiza resposta,
  gráfico, tabela, definição e SQL.

---

## 2. Arquitetura proposta

```
Streamlit UI  ──HTTP──>  FastAPI  ──>  IntentRouter ──> MetricRegistry
                                            │
                                            ▼
                                      QueryEngine (DuckDB, read-only)
                                            │
                                            ▼
                              AskResponse (answer, chart, table, definition, sql)
```

### Estrutura de pastas

```
app/
  api/main.py            # FastAPI: POST /ask, GET /metrics, GET /health
  core/models.py         # Pydantic: EventType, AskRequest, AskResponse, MetricSpec
  core/registry.py       # MetricRegistry com as 4 métricas
  core/router.py         # IntentRouter (keyword/sinônimo -> MetricSpec)
  core/engine.py         # QueryEngine: conexão DuckDB read-only + execução parametrizada
  core/charts.py         # helpers Plotly (figura -> JSON)
  data/generate.py       # gerador sintético seedado -> DuckDB/Parquet
  ui/streamlit_app.py    # front Streamlit
tests/                   # pytest por camada
docs/architecture.md     # este documento
```

### Contrato `AskResponse` (Pydantic)

| campo | tipo | descrição |
|---|---|---|
| `metric` | `str` | nome da métrica identificada |
| `answer` | `str` | texto gerado por **template** a partir do valor do banco — nunca por IA |
| `value` | `float \| None` | valor principal (ex.: taxa) quando aplicável |
| `definition` | `str` | definição da métrica (mesma fonte do `MetricSpec`) |
| `sql` | `str` | SQL exatamente como executado |
| `table` | `list[dict]` | linhas do resultado |
| `chart` | `dict` | figura Plotly serializada em JSON |
| `confidence` | `float` | score do matching da intenção |
| `matched` | `bool` | se a pergunta casou com alguma métrica |

Quando `matched = false`, os campos numéricos ficam vazios e `answer` explica que a
pergunta não corresponde a nenhuma métrica conhecida, listando as disponíveis.

---

## 3. Modelo de eventos

### Tabela `events` (grão = 1 evento por linha)

| coluna | tipo | descrição |
|---|---|---|
| `event_id` | UUID | id único do evento |
| `user_id` | str | id do usuário/conta |
| `event_type` | enum | ver `EventType` abaixo |
| `event_ts` | timestamp | quando ocorreu (UTC) |
| `properties` | JSON | atributos livres (ex.: `feature_name`, `step`, `plan`) |
| `session_id` | str | agrupa eventos de uma sessão |

### Tabela `users` (dimensão)

| coluna | tipo | descrição |
|---|---|---|
| `user_id` | str | id do usuário/conta |
| `signup_ts` | timestamp | data/hora do signup (UTC) |
| `plan` | str | plano (ex.: `free`, `pro`) |
| `country` | str | país |

### `EventType` (enum fechado — whitelist)

```
signup · onboarding_step_completed · project_created · feature_used
activated · login · session_start · subscription_started · subscription_cancelled
```

O enum ser **fechado** é parte da defesa anti-alucinação: apenas eventos conhecidos
entram no sistema, e as métricas só podem se referir a eles.

> **Nota (E2):** o conjunto foi estendido em relação ao rascunho inicial para cobrir
> os eventos exigidos pela camada de dados — `project_created`, `subscription_started`
> e `subscription_cancelled` (cancelamento, no lugar do genérico `churned`). Fonte de
> verdade do enum: `app/core/models.py`.

---

## 4. Definições das métricas

Cada métrica vira um `MetricSpec` que carrega **a mesma** definição textual mostrada
ao usuário **e** o template SQL executado — garantindo que definição e número
tenham uma única fonte de verdade.

### `activation_rate`

Usuários que atingiram o evento `activated` dividido pelo total de `signup`, numa
janela de **N dias após o signup** (default **7d**). "Activated" é o evento canônico
de primeiro valor (ex.: primeiro `feature_used` chave).

- **Retorna:** % de ativação + série temporal por coorte de signup.
- **Parâmetros:** janela em dias, intervalo de datas.

### `onboarding_funnel`

Contagem e taxa de conversão passo-a-passo dos `onboarding_step_completed`
(ex.: `step_1 → step_2 → step_3 → activated`).

- **Retorna:** tabela por passo (usuários, % do topo, % do passo anterior) + gráfico
  de funil.
- **Parâmetros:** ordem dos passos, intervalo de datas.

### `retention_d7`

Dos usuários que fizeram signup no dia **D**, a fração que teve pelo menos um evento
de atividade (`login` / `feature_used` / `session_start`) na janela **[D+7, D+8)** —
ou seja, **dia 7 exato** ("bounded / classic D7").

- **Decisão explícita:** usamos a definição de **dia exato**, não "unbounded ≥ D7".
  A alternativa fica registrada aqui para transparência; trocar de definição é uma
  mudança consciente de `MetricSpec`.
- **Retorna:** % de retenção D7 + curva por coorte.
- **Parâmetros:** intervalo de coortes.

### `feature_adoption`

Para uma feature X: usuários únicos com `feature_used`
(`properties.feature_name = X`) dividido por usuários ativos no período.

- **Retorna:** % de adoção por feature + ranking (gráfico de barras).
- **Parâmetros:** feature (default configurável), intervalo de datas.

---

## 5. Riscos de segurança e alucinação

### Segurança

- **SQL arbitrário / injection** — mitigado: nenhum SQL é gerado por IA nem pelo
  usuário. Apenas templates parametrizados da registry; parâmetros via binding do
  DuckDB, nunca concatenados.
- **Conexão read-only** — o `QueryEngine` abre o DuckDB em modo read-only; não há
  DDL/DML no caminho de request.
- **Validação de input** — `AskRequest` validado por Pydantic (tamanho máximo,
  tipos). A string livre da pergunta só é usada para matching de intenção, jamais
  interpolada em SQL.
- **DoS / queries pesadas** — `LIMIT` e timeout nos templates; janela temporal máxima.
- **Sem PII** — dados 100% sintéticos, sem dados reais de usuários.
- **CORS e erros** — FastAPI com CORS restrito; mensagens de erro que não vazam
  schema interno.

### Alucinação

- **Whitelist de métricas** — pergunta que não casa com nenhuma métrica gera uma
  resposta honesta ("não sei; estas são as métricas disponíveis"), nunca um chute.
- **Números só do banco** — `value`, `table` e `chart` derivam exclusivamente do
  resultado do SQL executado; a `answer` textual é montada por template a partir
  desse valor.
- **Transparência** — toda resposta expõe o SQL executado e a definição da métrica,
  tornando o resultado auditável.
- **Confidence + limiar** — matches fracos são sinalizados ou rejeitados.
- **Testes de contrato** — pytest garante que `answer`, `value` e `table` são
  consistentes entre si e derivam do mesmo resultado.

---

## 6. Entregas pequenas e testáveis (roadmap)

| # | Entrega | Artefato principal | Como testar |
|---|---|---|---|
| **E0** | Doc de arquitetura *(esta entrega)* | `docs/architecture.md` | Revisão das 6 seções |
| **E1** | Modelos Pydantic + `EventType` | `app/core/models.py` | Testes de validação |
| **E2** | Gerador sintético seedado | `app/data/generate.py` | Contagens determinísticas com seed fixo |
| **E3** | `MetricRegistry` + 4 `MetricSpec` | `app/core/registry.py` | Cada métrica tem definição, SQL e sinônimos |
| **E4** | `QueryEngine` (read-only) | `app/core/engine.py` | SQL de cada métrica roda e retorna o shape/valor esperado |
| **E5** | `IntentRouter` | `app/core/router.py` | Frases → métrica, incluindo o caso "não casa" |
| **E6** | API FastAPI | `app/api/main.py` | `TestClient` em `/ask`, `/metrics`, `/health` |
| **E7** | Charts Plotly | `app/core/charts.py` | Gera JSON válido por tipo de gráfico |
| **E8** | UI Streamlit | `app/ui/streamlit_app.py` | Smoke test / manual |
| **E9** | README + como rodar | `README.md`, deps | Instruções reproduzíveis |

Cada entrega tem testes próprios e pode ser commitada e validada isoladamente.
