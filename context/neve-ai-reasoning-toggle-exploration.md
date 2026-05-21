# Neve AI - Exploração do Toggle Rápido/Raciocínio

## 1. Toggle "Rápido/Raciocínio" - Frontend Implementation

### Localização Principal
- **Arquivo**: [src/lib/components/chat/MessageInput.svelte](src/lib/components/chat/MessageInput.svelte#L566)
- **Componentes**: Chat.svelte e MessageInput.svelte

### Variáveis de Estado
- **`thinkingEnabled`**: variável booleana (padrão `true`)
  - Definida em [Chat.svelte L169](src/lib/components/chat/Chat.svelte#L169)
  - Repassada via `bind:` para MessageInput.svelte
  - Controla se o raciocínio está habilitado ou desabilitado

### Lógica de Visibilidade do Botão
```typescript
// MessageInput.svelte L566-570
let showThinkingButton = false;
$: showThinkingButton = selectedModels.length > 0 && selectedModels.every(
    (model) => $models.find((m) => m.id === model)?.info?.meta?.capabilities?.toggle_reasoning ?? false
);
$: if (!showThinkingButton) {
    thinkingEnabled = true;  // Reset to fast mode if toggle not available
}
```

**Lógica**:
- Botão é exibido APENAS se todos os modelos selecionados têm `meta.capabilities.toggle_reasoning = true`
- Se o botão desaparece (modelo sem toggle), reseta para `thinkingEnabled = true` (Rápido)

### UI do Toggle (MessageInput.svelte L1720-2130)
- **Botão compacto**: [L2070-2090] exibe "Rápido" ou "Raciocínio" com ícone de chevron
- **Dropdown**: [L2093-2130] dois botões com ícones:
  - "Rápido" (ícone de raio) - `thinkingEnabled = false`
  - "Raciocínio" (ícone de lâmpada) - `thinkingEnabled = true`

## 2. Feature Toggle - Capabilidades do Modelo

### Definição de Capabilities
- **Arquivo**: [src/lib/components/workspace/Models/Capabilities.svelte](src/lib/components/workspace/Models/Capabilities.svelte#L54-L57)
- **Label**: "Toggle Reasoning"
- **Descrição**: "Show the Rápido/Raciocínio toggle in the message input bar"

### Predefined Features (Model Editor)
- **Arquivo**: [src/lib/components/workspace/Models/DefaultFeatures.svelte](src/lib/components/workspace/Models/DefaultFeatures.svelte)
- **Lista de Features**: `['web_search', 'image_generation', 'code_interpreter', 'code_execution', 'toggle_reasoning', 'stable_diffusion']`
- **Componente**: Usa checkboxes para marcar features padrão

### Model Editor Integration
- **Arquivo**: [src/lib/components/workspace/Models/ModelEditor.svelte](src/lib/components/workspace/Models/ModelEditor.svelte#L163)
- **Linha 163**: `info.meta.capabilities.toggle_reasoning = defaultFeatureIds.includes('toggle_reasoning');`
- **Linha 340-341**: Auto-habilitação de toggle_reasoning se a capability não for explicitamente false
- **Linha 661-666**: DefaultFeatures component com features disponíveis

## 3. Storage - Como Features São Armazenadas

### Modelo de Dados Backend
- **Arquivo**: [backend/neveai/models/models.py](backend/neveai/models/models.py#L40-L140)
- **Campo**: `meta: ModelMeta` (JSONField)
- **Estrutura**:
  ```python
  class ModelMeta:
      description: Optional[str] = None
      capabilities: Optional[dict] = None  # Contém toggle_reasoning e outras
  ```

### Predefined Settings nos Modelos Neve
- **Arquivo**: [backend/neveai/routers/llamacpp.py](backend/neveai/routers/llamacpp.py#L1410-L1500)
- **Lista Neve Catalog**: Define modelos com `default_feature_ids`
- **Exemplos**:
  - `"neve-echo-s"`: `"default_feature_ids": ["web_search", "toggle_reasoning"]`
  - `"neve-strata"`: `"default_feature_ids": ["code_execution", "toggle_reasoning"]`
  - `"neve-prism"`: `"default_feature_ids": []` (sem toggle_reasoning)

### Como Default Features São Aplicadas
- **Linha 1574-1590** em llamacpp.py:
  ```python
  default_feature_ids = entry.get("default_feature_ids", [])
  # ...
  "toggle_reasoning": "toggle_reasoning" in default_feature_ids,
  ```

## 4. Reasoning Tags - Processamento no Backend

### Tags de Raciocínio Padrão
- **Arquivo**: [backend/neveai/utils/middleware.py](backend/neveai/utils/middleware.py#L147-L151)
- **DEFAULT_REASONING_TAGS** (múltiplos formatos suportados):
  ```python
  [
      ("<think>", "</think>"),
      ("<thinking>", "</thinking>"),
      ("<reason>", "</reason>"),
      ("<reasoning>", "</reasoning>"),
      ("<thought>", "</thought>"),
      ("<Thought>", "</Thought>"),
      ("<|begin_of_thought|>", "<|end_of_thought|>"),
      ("▮think▮", "▮/think▮"),
  ]
  ```

### Parametrização de Tags
- **Arquivo**: [backend/neveai/utils/middleware.py](backend/neveai/utils/middleware.py#L3947-L3970)
- **Leitura de parâmetros**:
  ```python
  reasoning_tags_param = metadata.get("params", {}).get("reasoning_tags")
  DETECT_REASONING_TAGS = reasoning_tags_param is not False
  
  if isinstance(reasoning_tags_param, list) and len(reasoning_tags_param) == 2:
      reasoning_tags = [(reasoning_tags_param[0], reasoning_tags_param[1])]
  else:
      reasoning_tags = DEFAULT_REASONING_TAGS
  ```

### Payload OpenAI Format
- **Arquivo**: [backend/neveai/utils/payload.py](backend/neveai/utils/payload.py#L78)
- **Tipo**: `"reasoning_tags": list`
- Pode ser customizado por modelo nos params

## 5. No Think Flag - Desabilitar Raciocínio

### Frontend: Envio do Flag
- **Arquivo**: [src/lib/components/chat/Chat.svelte](src/lib/components/chat/Chat.svelte#L2637)
- **Código**:
  ```svelte
  ...(!thinkingEnabled ? { no_think: true } : {})
  ```
- O payload recebe `no_think: true` quando `thinkingEnabled = false` (modo Rápido)

### Backend: Aplicação do Flag
- **Arquivo**: [backend/neveai/routers/llamacpp.py](backend/neveai/routers/llamacpp.py#L1233-1240)
- **Extração**:
  ```python
  no_think = form_data.pop("no_think", False)
  ```
- **Aplicação ao payload**:
  ```python
  if no_think:
      payload["chat_template_kwargs"] = {"enable_thinking": False}
      payload["reasoning_format"] = "none"
  ```

### Injeção de Comando (Fallback)
- **Arquivo**: [backend/neveai/routers/llamacpp.py](backend/neveai/routers/llamacpp.py#L1555-1569)
- Se o modelo não suportar `chat_template_kwargs`, injeta `/no_think` no início da mensagem:
  ```python
  if no_think:
      for i in range(len(messages) - 1, -1, -1):
          if messages[i].get("role") == "user":
              messages[i]["content"] = "/no_think " + messages[i]["content"]
  ```

## 6. Renderização de Reasoning Content

### Componente Collapsible
- **Arquivo**: [src/lib/components/common/Collapsible.svelte](src/lib/components/common/Collapsible.svelte#L65-L300)
- **Detecção de tipo**: `isReasoning = attributes?.type === 'reasoning'`
- **Estados**:
  - `isDone`: raciocínio completou
  - `isStreaming`: raciocínio ainda em progresso
  - `showReasoningContent`: visibilidade do conteúdo

### Atributos do Bloco de Raciocínio
- `attributes.type = 'reasoning'`
- `attributes.done` = 'true' | 'false' (string)
- `attributes.duration` = segundos (para exibir "Thought for X seconds")

### UI do Bloco
- **Ícone**: Lightbulb quando reasoning, Terminal quando code_interpreter
- **Título dinâmico**: 
  - Streaming: "Thinking..." com shimmer
  - Done: "Thought for X seconds" ou "Thought for 2 hours"
- **Botão Copy**: Aparece quando raciocínio terminou (linha 207-230)
- **Gradients**: Fade-out para visualização compacta (preview mode)

## 7. Fluxo Completo

### Envio de Mensagem
1. User clica "Send" em MessageInput
2. `thinkingEnabled` determina se injeta `no_think: true`
3. Payload vai para backend com `{ no_think: true|false }`

### Processamento Backend
1. `generate_chat_completion()` lê `no_think`
2. Se `no_think = true`: injeta `/no_think` ou `enable_thinking=false`
3. LlamaCpp responde com ou sem tags de raciocínio
4. Middleware detecta tags usando `DEFAULT_REASONING_TAGS` ou custom params

### Renderização Frontend
1. Response streaming chega via WebSocket
2. Conteúdo com tags é parseado
3. Conteúdo dentro de tags cria bloco Collapsible com `type='reasoning'`
4. Bloco é expandido/colapsado com "Thought for X seconds"

## 8. State Management - Como é Coordenado

### Stores (Svelte)
- `$models`: Array de modelos com `info.meta.capabilities.toggle_reasoning`
- `selectedModels`: IDs dos modelos selecionados
- `thinkingEnabled`: Estado do toggle (Chat.svelte)

### Sincronização
- MessageInput.svelte monitora `$models` e `selectedModels`
- Calcula `showThinkingButton` reativamente
- Se modelo não suporta toggle, reseta para fast mode

### Persistência
- `thinkingEnabled` é LOCAL per chat session
- Não é salvo no banco (não persiste entre chats)
- Feature `toggle_reasoning` IS salvo em `model.meta.capabilities`

## 9. Padrões Identificados

### Feature Toggle Pattern
1. Feature definida em `DefaultFeatures.svelte` (disponível para seleção)
2. Salva em `defaultFeatureIds[]` array
3. Persistida em `model.meta.capabilities[feature_name]`
4. Lida em MessageInput via `$models[].info.meta.capabilities[feature_name]`
5. Aplicada em backend via `metadata.get("features", {})`

### Reasoning Content Pattern
1. Backend emite tags `<thinking>...</thinking>` na resposta
2. Middleware detecta as tags (customizável via params)
3. Frontend extrai conteúdo entre tags
4. Cria Collapsible block com `attributes.type = 'reasoning'`
5. UI renderiza com ícone, título dinâmico, e botão copy

