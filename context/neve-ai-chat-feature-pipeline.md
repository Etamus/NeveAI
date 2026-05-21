# Neve AI - Chat Feature Pipeline

- Chat feature toggles flow through `Chat.svelte` state + `getFeatures()`, `MessageInput.svelte`, and `MessageInput/InputMenu.svelte`.
- Backend feature prompt injection belongs in `backend/neveai/utils/middleware.py` after `features = form_data.pop(...)`, not in `utils/chat.py`.
- Artifact auto-open depends on `chatCodeExecutionEnabled`; new HTML artifact modes should set/derive `code_execution` true.
