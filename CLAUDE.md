# CLAUDE.md — Product Analytics Copilot

Instruções permanentes para trabalhar neste projeto. A fonte de verdade detalhada
das decisões de design é `docs/architecture.md`.

## Objetivo e escopo

Copilot de product analytics: o usuário faz perguntas em **linguagem natural** sobre
um produto SaaS e recebe **resposta em texto, gráfico, tabela, definição da métrica
e o SQL executado**. Escopo restrito às métricas registradas na whitelist — o sistema
não responde perguntas fora dela.

**Stack:** FastAPI · Streamlit · DuckDB · Pydantic · Plotly · pytest.

## Arquitetura aprovada

```
Streamlit UI → FastAPI → IntentRouter → MetricRegistry → QueryEngine (DuckDB, read-only) → AskResponse
```

- **IntentRouter** — mapeia a pergunta para um `MetricSpec` por keywords/sinônimos,
  com score e limiar. Abaixo do limiar → resposta honesta listando as métricas
  disponíveis. **Sem LLM.**
- **MetricRegistry** — cada métrica é um `MetricSpec` (Pydantic) com nome, sinônimos,
  definição textual, template SQL parametrizado e tipo de visualização.
- **QueryEngine** — executa o SQL da registry **read-only**, com parâmetros por
  binding. Nunca gera nem concatena SQL.
- **AskResponse** — contrato Pydantic de saída: `metric`, `answer`, `value`,
  `definition`, `sql`, `table`, `chart`, `confidence`, `matched`.

## Princípios para definição de métricas

- Toda métrica é um `MetricSpec` onde a **definição textual e o template SQL são a
  mesma fonte de verdade** — a definição mostrada ao usuário descreve exatamente o SQL
  executado.
- Métricas só se referem a eventos do enum fechado `EventType`.
- Escolhas de janela/semântica (ex.: `retention_d7` = dia 7 exato) são decisões
  explícitas documentadas no `MetricSpec` e em `docs/architecture.md`.
- Adicionar uma métrica = adicionar um `MetricSpec` completo (definição + SQL
  parametrizado + sinônimos + tipo de gráfico) e seus testes.

## Limites de segurança (invioláveis)

- **Nenhum SQL gerado por IA ou pelo usuário.** Só templates parametrizados da registry.
- Parâmetros sempre via **binding** do DuckDB, nunca concatenação de strings.
- Conexão DuckDB **read-only** no caminho de request; sem DDL/DML.
- A string livre da pergunta é usada **apenas** para matching de intenção, jamais
  interpolada em SQL.
- Input validado por Pydantic (tamanho máximo, tipos); `LIMIT`/timeout nos templates.
- Somente dados **sintéticos**, sem PII. CORS restrito; erros não vazam schema interno.

## Regras anti-alucinação (invioláveis)

- Números (`value`, `table`, `chart`) derivam **exclusivamente** do resultado do SQL.
- `answer` é montada por **template** a partir desse valor — nunca texto inventado.
- Pergunta sem match → resposta honesta ("não sei; métricas disponíveis: …"), nunca
  um chute.
- Toda resposta expõe o SQL e a definição (auditável).

## Convenções de código e estrutura

```
app/
  api/main.py            # FastAPI: POST /ask, GET /metrics, GET /health
  core/models.py         # Pydantic: EventType, AskRequest, AskResponse, MetricSpec
  core/registry.py       # MetricRegistry (as métricas)
  core/router.py         # IntentRouter
  core/engine.py         # QueryEngine (DuckDB read-only)
  core/charts.py         # helpers Plotly (figura -> JSON)
  data/generate.py       # gerador sintético seedado
  ui/streamlit_app.py    # front Streamlit
tests/                   # pytest por camada
docs/architecture.md     # decisões de design
```

- Toda estrutura de dados de entrada/saída é modelada com **Pydantic**.
- Gráficos como **JSON Plotly** (`core/charts.py`).
- Gerador de dados usa **seed fixo** — resultados reprodutíveis.
- Cada camada tem testes próprios em `tests/`; cada entrega é commitável isoladamente.

## Comandos obrigatórios de validação

Rodar antes de considerar qualquer mudança concluída:

```bash
pytest -q          # toda a suíte deve passar
```

*(À medida que a config for adicionada, incluir também lint/format — ex. `ruff check .`
e `ruff format --check .`. Não introduzir comandos que não existam ainda no repo.)*

## Decisões que NÃO devem ser alteradas sem aprovação

1. **Camada NL determinística, sem LLM** (whitelist + matching por keywords/sinônimos).
2. **Nenhum SQL gerado dinamicamente** — apenas templates parametrizados read-only.
3. **Dados sintéticos seedados**, sem PII.
4. **`EventType` como enum fechado.**
5. **Definições das métricas** (`activation_rate`, `onboarding_funnel`,
   `retention_d7` = dia 7 exato, `feature_adoption`) e a regra de **definição e SQL
   como fonte única de verdade**.
6. **Contrato `AskResponse`** como interface de saída.

Mudança em qualquer um destes exige aprovação explícita e atualização de
`docs/architecture.md`.
