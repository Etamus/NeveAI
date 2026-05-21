- Local model load presets live in `src/lib/components/chat/ModelSelector/LocalModelLoadPreferences.svelte` with storage helpers in `src/lib/utils/llamacppLoadPreferences.ts`.
- `cache_type` is not a model/chat advanced param anymore; it is a global local-load preset (`Padrão`, `Q8_0`, `Q4_0`, `FP16`) using localStorage key `llamacpp_cache_type`.
- Sidebar chat refresh loading text/spinner is intentionally hidden; keep the `Loader` sentinel functional without visible `Loading...` UI.
- ModelSettingsModal defaults are applied through backend effective defaults in `backend/neveai/utils/model_defaults.py`; unedited/local catalog models inherit them, while saves through `/api/v1/models/model/update` mark `meta.user_customized=true` and preserve user edits.

