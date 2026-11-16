# Agente de relatórios sobre SRAG

PoC (desafio AI Engineer, Indicium): um agente orquestrador consulta a base de SRAG do SUS e notícias em tempo real e gera um relatório com 4 métricas, 2 gráficos e comentários sobre o cenário atual.

Diagrama conceitual da arquitetura (PDF): [`docs/arquitetura.pdf`](docs/arquitetura.pdf)

![Arquitetura](docs/arquitetura.png)

## Como rodar
**Pré-requisitos:** Linux/WSL/macOS, Python 3.12 (no Ubuntu: `sudo apt install python3-venv`), cerca de 4 GB de RAM livres e ~3 GB de disco para o modelo. Não precisa de GPU nem de chave de API.

Rode tudo a partir da raiz do repositório:
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/download_data.py     # --date dd-mm-aaaa para outra versão do "banco vivo"
.venv/bin/python -m srag.ingest
```
LLM local (padrão, sem chave e sem custo). Instale o Ollama (pede `sudo`):
```
curl -fsSL https://ollama.com/install.sh | sh
```
Confirme que o serviço responde; se der erro de conexão, inicie-o **em outro terminal** e deixe aberto (o comando não retorna):
```
ollama list
ollama serve
```
Baixe o modelo (~2 GB); `ollama list` deve mostrá-lo depois. Sem ele, o `srag.run` falha com um erro HTTP do Ollama:
```
ollama pull qwen2.5:3b
```
Gerar o relatório e rodar os testes:
```
.venv/bin/python -m srag.run                    # cria reports/<run_id>/report.md + PNGs e logs/<run_id>.jsonl
.venv/bin/python -m pytest
```
Sem GPU, uma execução leva de 1 a 2 minutos. O modelo de 3B às vezes erra o formato ou cita notícia inexistente; o guardrail descarta o comentário (após uma tentativa de correção) e o relatório sai com um aviso explícito, sem inventar conteúdo.

**Outro provedor de LLM (opcional):** crie um `.env` na raiz com `LLM_PROVIDER=gemini` e `GEMINI_API_KEY=<sua chave>` (ou `LLM_PROVIDER=anthropic` e `ANTHROPIC_API_KEY=<sua chave>`). `LLM_MODEL` troca o modelo. O `.env` está no `.gitignore`.

## Arquitetura (e por quê)
- **Loop de tool use próprio sobre um LLM intercambiável**, sem framework de agentes: o fluxo é curto e fechado, e um loop explícito é mais simples de auditar do que um grafo.
- **3 tools** (`get_metrics`, `generate_charts`, `search_news`), com SQL fixo no DuckDB e sem SQL livre do modelo. O LLM decide a ordem das chamadas e a consulta de notícias, e redige os comentários. Se esquecer uma tool obrigatória, o código a chama e registra isso na auditoria.
- **Modelo dimensionado à tarefa:** `qwen2.5:3b` rodando local no Ollama por padrão: sem custo, sem chave e nenhum dado sai da máquina. `LLM_PROVIDER=gemini` ou `anthropic` troca de provedor e `LLM_MODEL` troca o modelo. O provedor fica atrás de uma interface mínima (`srag/llm.py`). Modelos pequenos erram mais, e é por isso que os guardrails e o preenchimento das tools pelo código existem. O modelo não calcula nada: só orquestra e escreve texto sobre agregados.
- **O LLM não escreve números.** Os valores do relatório vêm das tools, montados por template, com a origem (`tool_call_id`) de cada métrica.

Exemplo real de execução (relatório, gráficos e log de auditoria): [`docs/exemplo_execucao/`](docs/exemplo_execucao/). Para verificar a integridade: `sha256sum docs/exemplo_execucao/audit_log.jsonl` deve dar o mesmo valor registrado na seção "Auditoria" do relatório.

## Governança e transparência
- **Log JSONL por execução** (`logs/<run_id>.jsonl`): chamadas de tool (parâmetros e resultado), cada turno do LLM (texto, tokens, modelo), tools forçadas pelo código, falhas e bloqueios de guardrail. Chaves e tokens são redigidos.
- **Reprodutibilidade:** o relatório registra `run_id`, modelo, arquivos de origem, data de ingestão, hash da base limpa e o **sha256 do log**.
- **Notícias:** snapshot salvo em `cache/news_<run_id>.json`, com fonte, data e link de cada notícia citada.
- Se as notícias falharem, o relatório sai com aviso explícito, sem inventar contexto.

## Guardrails
1. Allowlist de tools; tool desconhecida é bloqueada e auditada.
2. Comentários do LLM sem dígitos e com ao menos uma URL que tenha vindo de `search_news`; caso contrário são descartados.
3. Texto de notícia tratado como dado não confiável: só título/fonte/data/link, sem caracteres de controle, tamanho limitado, em bloco delimitado com instrução de ignorar ordens.
4. Limite de 6 iterações por execução.

## Dados sensíveis
A base aberta não traz nomes, mas permite reidentificação. A ingestão mantém **apenas 9 colunas** (3 datas e 6 códigos); data de nascimento, idade, sexo, raça, município, UF e unidade de saúde são descartados antes de qualquer outra etapa. Datas impossíveis viram nulo. O LLM recebe somente agregados. `data/`, `.env`, `logs/`, `cache/` e `reports/` ficam fora do Git. Um teste garante que a base limpa só tem colunas permitidas. A base é pública e anonimizada (dados abertos do SUS, LGPD).

## Definição das métricas
Janelas ajustadas terminam 14 dias antes da data de referência, por causa do atraso de notificação; a taxa bruta aparece ao lado. Casos são datados pelo início dos sintomas.

| Métrica | Cálculo |
|---|---|
| Aumento de casos | casos dos últimos 30 dias vs. 30 dias anteriores (janela ajustada) |
| Mortalidade | óbitos (`EVOLUCAO`=2) / casos com cura ou óbito, últimos 12 meses; óbito por outras causas e casos em aberto ficam fora (% em aberto é reportado) |
| UTI | **aproximação:** internados (`HOSPITAL`=1) que passaram por UTI / internados com resposta válida. A base não tem capacidade de leitos, então não é ocupação |
| Vacinação | **aproximação:** casos de SRAG com `VACINA_COV`=1 / com resposta válida. Não é cobertura populacional e há viés de seleção |

Códigos 9 e nulos ficam fora dos denominadores.

## Limitações
- O atraso de notificação faz os números mais recentes subirem depois; por isso o gráfico diário marca a faixa de subnotificação.
- Google News RSS não tem garantia de serviço; há cache do snapshot e aviso em caso de falha.
- A base é um "banco vivo": reexecutar com outra versão muda os números (a versão fica registrada).

## Estrutura
`srag/` (`ingest`, `metrics`, `charts`, `news`, `guardrails`, `audit`, `agent`, `report`, `run`), `scripts/download_data.py`, `tests/` (LLM mockado, Parquet sintético, guardrails e privacidade), `docs/`.
