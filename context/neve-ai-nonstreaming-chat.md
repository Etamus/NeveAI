- Non-stream local chat uses `backend/neveai/utils/middleware.py::non_streaming_chat_response_handler`; it needs `form_data = ctx["form_data"]` before calling `should_hide_reasoning_output(form_data, metadata)`.
- If Stream de resposta is off and chat hangs with no final message, check for swallowed exceptions in this non-stream handler; missing event emission leaves the frontend waiting on `chat:completion`.
- `backend/neveai/routers/llamacpp.py` must not `pop("no_think")`; preserve it on `form_data` so final middleware can hide `<think>...</think>` in non-stream responses.

