# Neve AI - Tarefas de Background Pós-Chat (Relatório Final)

## 1. ARQUIVOS E FUNÇÕES RELEVANTES

### Arquivos Principais
| Arquivo | Localização | Função |
|---------|-------------|--------|
| [middleware.py](d:\Neve AI\backend\neveai\utils\middleware.py#L3335) | Linha 3335 | `async def background_tasks_handler(ctx)` - Gerencia tarefas de background |
| [tasks.py](d:\Neve AI\backend\neveai\routers\tasks.py) | Linhas 179, 263, 336 | Funções de geração: `generate_title()`, `generate_follow_ups()`, `generate_chat_tags()` |
| [main.py](d:\Neve AI\backend\neveai\main.py#L1751) | Linha 1751 | Ponto de entrada: `tasks = form_data.pop("background_tasks", None)` |
| [config.py](d:\Neve AI\backend\neveai\config.py) | - | Flags de configuração (ENABLE_*_GENERATION) |
| [constants.py](d:\Neve AI\backend\neveai\constants.py#L113) | Linha 113 | Enum TASKS com 9 tipos de tarefas |

### Imports Críticos em middleware.py (linha ~40)
```python
from neveai.routers.tasks import (
    generate_title,
    generate_follow_ups,
    generate_chat_tags,
)
```

### Triggers do Handler
- Linha 3680: Após resposta não-streaming salva no BD
- Linha 5263: Após stream completa (asyncio.CancelledError handling)

---

## 2. TAREFAS PÓS-GERAÇÃO QUE CONSOMEM O MODELO/LLM (3 total)

### Task 1: Geração de Título
- **Arquivo**: [tasks.py#L179](d:\Neve AI\backend\neveai\routers\tasks.py#L179)
- **Constante**: `TASKS.TITLE_GENERATION = "title_generation"`
- **Flag de Controle**: `ENABLE_TITLE_GENERATION` (config.py)
- **Função**: `async def generate_title(request, form_data, user)`
- **Modelo Usado**: `TASK_MODEL` ou `TASK_MODEL_EXTERNAL` (ou fallback para modelo atual)
- **Condições**:
  - Task deve estar habilitada em `form_data["background_tasks"]`
  - Chat não pode ser temporário (não começa com "local:")
  - `tasks[TASKS.TITLE_GENERATION]` deve ser True
  - Será usada apenas se `len(messages) > 2` OU chat tem mensagem de sistema
- **Lógica no Handler** (middleware.py, linhas 3448-3511):
  - Chama `generate_title()` com mensagens do chat
  - Extrai JSON da resposta para obter `{title: "..."}`
  - Se vazio, usa primeira mensagem como título
  - **DB Update**: `Chats.update_chat_title_by_id(metadata["chat_id"], title)`
  - **Evento**: Emite `"chat:title"` via WebSocket
  - Linha 3407-3408: Insere follow-ups na mensagem se existirem

### Task 2: Geração de Perguntas de Acompanhamento (Follow-ups)
- **Arquivo**: [tasks.py#L263](d:\Neve AI\backend\neveai\routers\tasks.py#L263)
- **Constante**: `TASKS.FOLLOW_UP_GENERATION = "follow_up_generation"`
- **Flag de Controle**: `ENABLE_FOLLOW_UP_GENERATION` (config.py)
- **Função**: `async def generate_follow_ups(request, form_data, user)`
- **Modelo Usado**: `TASK_MODEL` ou `TASK_MODEL_EXTERNAL` (ou fallback)
- **Condições**:
  - Task deve estar habilitada em `form_data["background_tasks"]`
  - `tasks[TASKS.FOLLOW_UP_GENERATION]` deve ser True
- **Lógica no Handler** (middleware.py, linhas 3392-3427):
  - Chama `generate_follow_ups()` com mensagens do chat
  - Extrai JSON da resposta para obter `{follow_ups: [...]}`
  - **DB Update**: `Chats.upsert_message_to_chat_by_id_and_message_id()` com `followUps`
  - **Evento**: Emite `"chat:message:follow_ups"` com lista de perguntas
  - Linha 3432-3433: Salva no banco

### Task 3: Geração de Tags do Chat
- **Arquivo**: [tasks.py#L336](d:\Neve AI\backend\neveai\routers\tasks.py#L336)
- **Constante**: `TASKS.TAGS_GENERATION = "tags_generation"`
- **Flag de Controle**: `ENABLE_TAGS_GENERATION` (config.py)
- **Função**: `async def generate_chat_tags(request, form_data, user)`
- **Modelo Usado**: `TASK_MODEL` ou `TASK_MODEL_EXTERNAL` (ou fallback)
- **Condições**:
  - Task deve estar habilitada em `form_data["background_tasks"]`
  - Chat não pode ser temporário (não começa com "local:")
  - `tasks[TASKS.TAGS_GENERATION]` deve ser True
- **Lógica no Handler** (middleware.py, linhas 3514-3548):
  - Chama `generate_chat_tags()` com mensagens do chat
  - Extrai JSON da resposta para obter `{tags: [...]}`
  - **DB Update**: `Chats.update_chat_tags_by_id(metadata["chat_id"], tags, user)`
  - **Evento**: Emite `"chat:tags"` com lista de tags

---

## 3. TAREFAS PÓS-GERAÇÃO NÃO-LLM QUE RODAM EM BACKGROUND (2 main)

### Background Task 1: Notificações de Webhook
- **Localização**: middleware.py, linhas 3660-3679 e 5241-5259
- **Função**: `await post_webhook()`
- **Imports**: `from neveai.utils.webhook import post_webhook` (linha 62)
- **Condições**:
  - Chamada se `not Users.is_user_active(user.id)` (usuário não está ativo)
  - Verifica `webhook_url = Users.get_user_webhook_url_by_id(user.id)`
  - Requer webhook URL configurado no usuário
- **Dados Enviados**:
  ```python
  await post_webhook(
      request.app.state.WEBUI_NAME,
      webhook_url,
      message_content,
      {
          "action": "chat",
          "message": content,
          "title": title,
          "url": f"{WEBUI_URL}/c/{chat_id}",
      }
  )
  ```
- **Tipo**: Notificação assíncrona (não bloqueia resposta)
- **Sem flag de controle** (sempre executa se condições atendidas)

### Background Task 2: Atualizações de Banco de Dados
- **Localização**: Multiple locations em middleware.py
- **Múltiplas Operações**:
  1. **Salvar Follow-ups** (line 3432): `Chats.upsert_message_to_chat_by_id_and_message_id(chat_id, message_id, {followUps})`
  2. **Atualizar Título** (line 3493): `Chats.update_chat_title_by_id(chat_id, title)`
  3. **Atualizar Tags** (line 3527): `Chats.update_chat_tags_by_id(chat_id, tags, user)`
  4. **Outras**: Metadata, errors, selectedModelId, etc. em `non_streaming_chat_response_handler`
- **Tipo**: Operações síncronas ao BD (não async dentro do handler)
- **Sem flag específica** (executa conforme resultado das gerações)

### Background Task 3: Atualizar Última Atividade do Usuário
- **Localização**: [auth.py](d:\Neve AI\backend\neveai\utils\auth.py), linhas 330 e 394
- **Função**: `Users.update_last_active_by_id(user.id)`
- **Como**: Adicionada via FastAPI `BackgroundTasks` (não relacionada a `background_tasks_handler`)
- **Momento**: Após login/verificação de token
- **Tipo**: Atualização de timestamp assíncrona

---

## 4. FLAGS/CONFIGURAÇÕES QUE HABILITAM/DESABILITAM

| Flag | Arquivo | Descrição | Tarefas Afetadas |
|------|---------|-----------|------------------|
| `ENABLE_TITLE_GENERATION` | config.py | Habilita geração automática de títulos | Task 1 |
| `ENABLE_FOLLOW_UP_GENERATION` | config.py | Habilita geração de perguntas acompanhamento | Task 2 |
| `ENABLE_TAGS_GENERATION` | config.py | Habilita geração automática de tags | Task 3 |
| `TASK_MODEL` | config.py | Modelo customizado para tasks (sobrescreve modelo atual) | Task 1, 2, 3 |
| `TASK_MODEL_EXTERNAL` | config.py | Endpoint externo para tarefas | Task 1, 2, 3 |
| `ENABLE_AUTOCOMPLETE_GENERATION` | config.py | Habilita autocompletar (endpoint apenas, não background) | - |
| `ENABLE_SEARCH_QUERY_GENERATION` | config.py | Habilita geração de queries web search | Não background |
| `ENABLE_RETRIEVAL_QUERY_GENERATION` | config.py | Habilita geração de queries RAG | Não background |

### Como Habilitadas no Frontend
- Frontend envia `form_data["background_tasks"]` com dict:
  ```python
  {
      "title_generation": bool,      # ENABLE_TITLE_GENERATION
      "tags_generation": bool,       # ENABLE_TAGS_GENERATION
      "follow_up_generation": bool   # ENABLE_FOLLOW_UP_GENERATION
  }
  ```
- Lógica no frontend (arquivo .js minificado): 
  - Disable se é o primeiro turno (1-2 mensagens)
  - Disable tags/title para chats locais
  - Habilita conforme flags e condições

---

## 5. EVIDÊNCIAS COM CAMINHOS E LINHAS

### Entry Point
- **Arquivo**: [main.py](d:\Neve AI\backend\neveai\main.py#L1751)
- **Linha 1751**: `tasks = form_data.pop("background_tasks", None)`

### Handler Principal
- **Arquivo**: [middleware.py](d:\Neve AI\backend\neveai\utils\middleware.py#L3335)
- **Função**: `async def background_tasks_handler(ctx)` - linha 3335
- **Calls ao handler**:
  - Linha 3680: `await background_tasks_handler(ctx)` (non-streaming)
  - Linha 5263: `await background_tasks_handler(ctx)` (streaming)

### Funções de Geração LLM
1. **Title**: [tasks.py#L179](d:\Neve AI\backend\neveai\routers\tasks.py#L179)
2. **Follow-ups**: [tasks.py#L263](d:\Neve AI\backend\neveai\routers\tasks.py#L263)
3. **Tags**: [tasks.py#L336](d:\Neve AI\backend\neveai\routers\tasks.py#L336)

### Lógica do Handler
- **Follow-up check**: Line 3392 - `if (TASKS.FOLLOW_UP_GENERATION in tasks and tasks[TASKS.FOLLOW_UP_GENERATION]):`
- **Title check**: Line 3448 - `if tasks[TASKS.TITLE_GENERATION]:`
- **Tags check**: Line 3514 - `if TASKS.TAGS_GENERATION in tasks and tasks[TASKS.TAGS_GENERATION]:`

### DB Updates
- **Follow-ups save**: Line 3432 - `Chats.upsert_message_to_chat_by_id_and_message_id(..., {followUps})`
- **Title update**: Line 3493 - `Chats.update_chat_title_by_id(..., title)`
- **Tags update**: Line 3527 - `Chats.update_chat_tags_by_id(..., tags, user)`

### Eventos WebSocket
- **Follow-ups**: Line 3420 - `await event_emitter({"type": "chat:message:follow_ups", ...})`
- **Title**: Line 3500 - `await event_emitter({"type": "chat:title", ...})`
- **Tags**: Line 3541 - `await event_emitter({"type": "chat:tags", ...})`

### Webhook Notification
- **Non-streaming**: Lines 3660-3679 - Check user active + post_webhook
- **Streaming**: Lines 5241-5259 - Same logic in streaming handler
- **Condition**: Line 3663 - `if not Users.is_user_active(user.id):`

### TASKS Enum
- **Arquivo**: [constants.py](d:\Neve AI\backend\neveai\constants.py#L113) - Linha 113
- **Constantes**:
  ```python
  TITLE_GENERATION = "title_generation"           # Linha 116
  FOLLOW_UP_GENERATION = "follow_up_generation"   # Linha 117
  TAGS_GENERATION = "tags_generation"             # Linha 118
  EMOJI_GENERATION = "emoji_generation"           # Linha 119
  QUERY_GENERATION = "query_generation"           # Linha 120
  IMAGE_PROMPT_GENERATION = "image_prompt_generation" # Linha 121
  AUTOCOMPLETE_GENERATION = "autocomplete_generation" # Linha 122
  FUNCTION_CALLING = "function_calling"           # Linha 123
  MOA_RESPONSE_GENERATION = "moa_response_generation" # Linha 124
  ```

---

## RESUMO EXECUTIVO

### Tarefas de Background Pós-Chat (Ordem de Execução)

1. **Webhook Notification** (se aplicável) → Notifica sistemas externos
2. **Follow-Up Generation** (LLM) → Gera perguntas de acompanhamento
3. **Title Generation** (LLM) → Gera título do chat
4. **Tags Generation** (LLM) → Gera tags automáticas
5. **Database Updates** → Persiste todos os resultados

### Consumo de LLM
- **Modelos que podem ser usados**: 
  - `TASK_MODEL` (configuração global)
  - `TASK_MODEL_EXTERNAL` (endpoint externo)
  - Fallback para modelo original se não configurado
- **Max tokens**: Definido por modelo, padrão ~1000 tokens
- **Streaming**: Nunca (todas as tasks usam `stream: False`)

### Flags Independentes
Cada uma das 3 tarefas LLM pode ser habilitada/desabilitada independentemente via config + form_data

### Tasks NOT em Background
- Image Prompt Generation (manual endpoint)
- Query Generation (manual endpoint)
- Autocompletion (manual endpoint)
- Emoji Generation (manual endpoint)
- MOA Response Generation (manual endpoint)
