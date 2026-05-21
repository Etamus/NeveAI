# Neve AI Background Tasks Exploration

## TASKS Enum (constants.py, line 113)
```
TITLE_GENERATION = "title_generation"
FOLLOW_UP_GENERATION = "follow_up_generation"  
TAGS_GENERATION = "tags_generation"
EMOJI_GENERATION = "emoji_generation"
QUERY_GENERATION = "query_generation"
IMAGE_PROMPT_GENERATION = "image_prompt_generation"
AUTOCOMPLETE_GENERATION = "autocomplete_generation"
FUNCTION_CALLING = "function_calling"
MOA_RESPONSE_GENERATION = "moa_response_generation"
```

## Main Handler
- **Location**: [middleware.py](d:\Neve AI\backend\neveai\utils\middleware.py#L3335) line 3335
- **Function**: `async def background_tasks_handler(ctx)`
- **Called from**: 
  - middleware.py line 3680 (non-streaming response)
  - middleware.py line 5263 (streaming response)
- **Called after**: Message saved to database

## Context Object (ctx)
- `request`: Request object
- `form_data`: Chat completion request data
- `user`: User object  
- `metadata`: Chat metadata (chat_id, message_id, session_id, user_id)
- `tasks`: Dict of enabled background tasks (passed from form_data["background_tasks"])
- `event_emitter`: Event emitter for WebSocket updates
- `event_caller`: Event caller function
- `model`: Model object

## Background Tasks - CALLED IN HANDLER (consume LLM)

### 1. Title Generation
- **Flag**: `ENABLE_TITLE_GENERATION` (config.py)
- **Function**: `generate_title()` - [tasks.py](d:\Neve AI\backend\neveai\routers\tasks.py#L179) line 179
- **Task**: TASKS.TITLE_GENERATION
- **Handler logic**: 
  - Line 3448-3515 in middleware.py
  - Only for non-temp chats (not starting with "local:")
  - Generates title via LLM
  - Updates chat via `Chats.update_chat_title_by_id()`
  - Emits "chat:title" event

### 2. Follow-Up Generation
- **Flag**: `ENABLE_FOLLOW_UP_GENERATION` (config.py)
- **Function**: `generate_follow_ups()` - [tasks.py](d:\Neve AI\backend\neveai\routers\tasks.py#L263) line 263
- **Task**: TASKS.FOLLOW_UP_GENERATION  
- **Handler logic**:
  - Line 3395-3426 in middleware.py
  - Generates follow-up questions via LLM
  - Emits "chat:message:follow_ups" event
  - Updates message with `Chats.upsert_message_to_chat_by_id_and_message_id()`

### 3. Tags Generation
- **Flag**: `ENABLE_TAGS_GENERATION` (config.py)
- **Function**: `generate_chat_tags()` - [tasks.py](d:\Neve AI\backend\neveai\routers\tasks.py#L336) line 336
- **Task**: TASKS.TAGS_GENERATION
- **Handler logic**:
  - Line 3514-3545 in middleware.py
  - Only for non-temp chats
  - Generates tags via LLM
  - Updates chat via `Chats.update_chat_tags_by_id()`
  - Emits "chat:tags" event

## Endpoints - NOT integrated in background handler (manual call)
- `generate_image_prompt()` - /image_prompt/completions - TASKS.IMAGE_PROMPT_GENERATION
- `generate_queries()` - /queries/completions - TASKS.QUERY_GENERATION (web_search/retrieval)
- `generate_autocompletion()` - /autocomplete/completions - TASKS.AUTOCOMPLETE_GENERATION (flag: ENABLE_AUTOCOMPLETE_GENERATION)
- `generate_emoji()` - /emoji/completions - TASKS.EMOJI_GENERATION
- `generate_moa_response()` - /moa/completions - TASKS.MOA_RESPONSE_GENERATION

## Configuration
- **Task Model**: `TASK_MODEL` / `TASK_MODEL_EXTERNAL`
- **Enable Flags**: 
  - ENABLE_TITLE_GENERATION
  - ENABLE_FOLLOW_UP_GENERATION
  - ENABLE_TAGS_GENERATION
  - ENABLE_AUTOCOMPLETE_GENERATION
  - ENABLE_SEARCH_QUERY_GENERATION
  - ENABLE_RETRIEVAL_QUERY_GENERATION

## Background Tasks - NON-MODEL (Database/Async)
From [middleware.py](d:\Neve AI\backend\neveai\utils\middleware.py#L3660):
- **Webhook notifications** - `post_webhook()` 
  - Called when user is NOT active
  - Notifies external systems about chat completion
  - Location: middleware.py lines 3668 and 5244
  
- **Message save to database** - `Chats.upsert_message_to_chat_by_id_and_message_id()`
  - Multiple calls:
    - Line 3407: Save follow_ups
    - Line 3483: Update message with follow_ups
    - Line 3550: Update message with title
    - Other places for errors/metadata

From [auth.py](d:\Neve AI\backend\neveai\utils\auth.py):
- `Users.update_last_active_by_id(user.id)` - added via FastAPI BackgroundTasks (lines 330, 394)

## Entry Point for background_tasks
- Location: [main.py](d:\Neve AI\backend\neveai\main.py#L1751) line 1751
- `tasks = form_data.pop("background_tasks", None)`
- Passed in POST request body from frontend
- Contains dict like: `{title_generation: bool, tags_generation: bool, follow_up_generation: bool}`

## Handler Call Triggers
1. **Non-streaming response** - middleware.py line 3680
   - After message saved to database
   - After webhook notification sent
   
2. **Streaming response** - middleware.py line 5263
   - After stream completes
   - After final event emitted
   - In try/except with asyncio.CancelledError handling

## Flags Configuration (all in config.py)
- `ENABLE_TITLE_GENERATION` - Enable title generation via LLM
- `ENABLE_FOLLOW_UP_GENERATION` - Enable follow-up questions via LLM
- `ENABLE_TAGS_GENERATION` - Enable auto tagging via LLM
- `ENABLE_AUTOCOMPLETE_GENERATION` - Enable text completion (endpoint only, not background)
- `ENABLE_SEARCH_QUERY_GENERATION` - Enable web search query generation
- `ENABLE_RETRIEVAL_QUERY_GENERATION` - Enable RAG query generation
- `TASK_MODEL` - Custom model for task generation (overrides model-specific)
- `TASK_MODEL_EXTERNAL` - External model endpoint for tasks

## Summary

### POST-GENERATION TASKS THAT CONSUME LLM (3 total):
1. Title Generation (configurable: ENABLE_TITLE_GENERATION)
2. Follow-Up Questions (configurable: ENABLE_FOLLOW_UP_GENERATION)
3. Tags Generation (configurable: ENABLE_TAGS_GENERATION)

### POST-GENERATION TASKS THAT DON'T CONSUME LLM (2 main):
1. Webhook Notifications (conditional: user not active)
2. Database Updates (message metadata, tags, follow-ups, title)

### ENDPOINTS NOT IN BACKGROUND (need manual calls):
1. Image Prompt Generation (TASKS.IMAGE_PROMPT_GENERATION)
2. Query Generation - web_search/retrieval (TASKS.QUERY_GENERATION)
3. Autocompletion (TASKS.AUTOCOMPLETE_GENERATION, flag: ENABLE_AUTOCOMPLETE_GENERATION)
4. Emoji Generation (TASKS.EMOJI_GENERATION)
5. MOA Response Generation (TASKS.MOA_RESPONSE_GENERATION)
