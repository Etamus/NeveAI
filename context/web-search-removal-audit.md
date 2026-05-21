# Web Search Removal Audit - Neve AI

## Backend Status
- Web search endpoints (`/process/web`, `/process/web/search`, `/process/youtube`) are ALREADY REMOVED from routers/retrieval.py
- Config shows web_search is hardcoded to `False` in config endpoints
- `processYoutubeVideo` and `processWebSearch` API clients exist but have no backend endpoints to call
- Backend is already in disabled state

## Frontend Active References Found

### API Functions (Export Layer)
- `src/lib/apis/retrieval/index.ts` - Lines 286-380+
  - `processYoutubeVideo()` - function exported but no endpoint exists
  - `processWeb()` - function exported but no endpoint exists  
  - `processWebSearch()` - function exported but no endpoint exists

### Chat Component
- `src/lib/components/chat/Chat.svelte`
  - Line 78: Import of processWeb, processWebSearch, processYoutubeVideo
  - Line 159: `webSearchEnabled` variable
  - Lines 546-550: Capability check and auto-enable logic
  - Lines 2371-2395: Features config building web_search flag
  - Lines 1139-1140: Usage in knowledge base processing

### Settings UI
- `src/lib/components/chat/Settings/Interface.svelte`
  - Line 96: `webSearch` local state
  - Lines 174-176: `toggleWebSearch()` function
  - Line 258: Load from $settings?.webSearch

### Message Input
- `src/lib/components/chat/MessageInput.svelte`
  - Line 131: `webSearchEnabled` prop export
  - Lines 500-502: Model capability check for web_search
  - Lines 529-531: Show web search button logic
  - Lines 1426-1860: UI bindings for web search toggle

### Status Display
- `src/lib/components/chat/Messages/ResponseMessage/WebSearchResults.svelte` - ENTIRE COMPONENT
- `src/lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte`
  - Lines 24, 40, 91: Display web_search status results

### Admin Settings
- `src/lib/components/admin/Settings/WebSearch.svelte` - ENTIRE COMPONENT
- `src/lib/components/admin/Settings/Models/ModelSettingsModal.svelte` - Line 307
- `src/lib/components/admin/Users/Groups/Permissions.svelte` - Lines 742-744

### Workspace Models
- `src/lib/components/workspace/Models/DefaultFeatures.svelte` - Lines 10, 36
- `src/lib/components/workspace/Models/Capabilities.svelte` - Lines 22, 68
- `src/lib/components/workspace/Models/BuiltinTools.svelte` - Line 26
- `src/lib/components/workspace/Models/ModelEditor.svelte` - Line 665

### App Store
- `src/lib/stores/index.ts`
  - Line 161: `webSearch?: any;` in Settings type
  - Line 238: `enable_web_search?: boolean;` in Config features type

### Knowledge Base
- `src/lib/components/workspace/Knowledge/KnowledgeBase.svelte`
  - Line 37: Import processWeb, processYoutubeVideo
  - Line 211: Usage in knowledge base web processing

### Backend Config
- `backend/neveai/routers/llamacpp.py`
  - Lines 1370, 1388, 1397: web_search in capabilities and default_feature_ids

- `backend/neveai/routers/tasks.py`
  - Line 474: Type check "web_search" in queries endpoint

- `backend/neveai/routers/retrieval.py`
  - WebConfig class and ENABLE_WEB_SEARCH config management
  - Hardcoded to False in multiple places
