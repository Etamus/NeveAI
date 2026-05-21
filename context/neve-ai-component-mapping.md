# Neve AI - Component Mapping

## IMPORTANT: Use the correct files!

- **Integration toggles menu** (Mais/+): `src/lib/components/chat/MessageInput/InputMenu.svelte` (NOT IntegrationsMenu.svelte)
- **System Prompt / Controls side panel**: `src/lib/components/chat/ModelSettingsSheet.svelte` (NOT Controls/Controls.svelte which is orphaned/unused)
- **Chat side drawer** (Artifacts, Embeds, Terminal): `src/lib/components/chat/ChatControls.svelte`
- **Navbar 3-dot menu**: `src/lib/components/layout/Navbar/Menu.svelte`
- **Model selector dropdown**: `src/lib/components/chat/ModelSelector/Selector.svelte`
- **Main chat input bar**: `src/lib/components/chat/MessageInput.svelte` (has inline toggle pills)
- **Chat page**: `src/lib/components/chat/Chat.svelte`
- **Thinking/Reasoning block**: `src/lib/components/common/Collapsible.svelte` (Unsloth Studio style: lightbulb icon, rotating chevron, border on open, max-h scroll, fade gradients, copy button)
- **Thinking shimmer CSS**: `src/app.css` lines ~209-234
- **Web search results**: `src/lib/components/chat/Messages/ResponseMessage/WebSearchResults.svelte` (Unsloth-style: globe icon, badge pills, auto-collapse, +X more)
- **Status history items**: `src/lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte`

## Build & Deploy
```powershell
cd "d:\Neve AI"; npm run build 2>&1 | Select-Object -Last 5
Copy-Item -Path "d:\Neve AI\build\*" -Destination "d:\Neve AI\backend\open_webui\frontend" -Recurse -Force
```
