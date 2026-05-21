# Neve AI - Disabled/Hidden Frontend Features Report
**Generated**: 6 May 2026 | **Scope**: src/ frontend source only | **Status**: Complete exploration

---

## 1. SERVER-CONTROLLED FEATURE FLAGS ($config.features.*)
These are disabled by default at the backend and gate UI components.

### Default FALSE (Not visible unless enabled):
- **enable_notes** → [src/routes/(app)/notes/+layout.svelte](src/routes/\(app\)/notes/+layout.svelte#L13), [src/lib/components/layout/Sidebar.svelte](src/lib/components/layout/Sidebar.svelte#L788)
  - Controls: Notes workspace tab, note creation/editing UI
  - Usage: `{#if ($config?.features?.enable_notes ?? false) && ...}`
  
- **enable_direct_connections** → [src/lib/components/workspace/Models.svelte](src/lib/components/workspace/Models.svelte#L127), [src/routes/+layout.svelte](src/routes/+layout.svelte#L463) 
  - Controls: Direct connection UI for models (commented as "disabled for Neve AI - uses server-side llamacpp")
  - Files: Models edit, chat model selection
  
- **enable_community_sharing** → [src/lib/components/workspace/Tools.svelte](src/lib/components/workspace/Tools.svelte#L493), [src/lib/components/workspace/Prompts.svelte](src/lib/components/workspace/Prompts.svelte#L529)
  - Controls: Share button/menu in Tools, Prompts, Models
  - Usage: Show "Share" action menu items

- **enable_api_keys** → [src/lib/components/chat/Settings/Account.svelte](src/lib/components/chat/Settings/Account.svelte#L255)
  - Controls: API Keys management in user settings
  
- **enable_admin_export** → [src/lib/components/admin/Settings/Database.svelte](src/lib/components/admin/Settings/Database.svelte#L118)
  - Controls: Admin database export functionality

### Default TRUE (Can be disabled):
- **enable_admin_analytics** → [src/routes/(app)/admin/analytics/+page.svelte](src/routes/\(app\)/admin/analytics/+page.svelte#L14)
  - DEFAULT: true, can be disabled
  - Controls: Entire admin analytics page visibility
  
- **enable_websocket** → [src/routes/+layout.svelte](src/routes/+layout.svelte#L774)
  - DEFAULT: true, gates WebSocket setup
  - Controls: Real-time socket connection initialization

- **enable_version_update_check** → [src/routes/(app)/+layout.svelte](src/routes/\(app\)/+layout.svelte#L342)
  - Controls: Version update checking (admin only)

---

## 2. UI STATE STORES (Visibility Toggles - Default FALSE)
All in [src/lib/stores/index.ts](src/lib/stores/index.ts) - initialized false, shown on user interaction:

**Sidebar/Navigation:**
- `showSidebar` - Sidebar visibility
- `showSearch` - Search modal
- `showSettings` - Settings modal

**Chat Features:**
- `showControls` - Model controls panel
- `showModelSettings` - Model settings
- `showEmbeds` - Embed view
- `showOverview` - Chat overview
- `showArtifacts` - Code artifacts display
- `showCallOverlay` - Call/video overlay
- `showFileNav` - File navigation panel

**Admin/Workspace:**
- `showAdminModelsModal` - Add models modal
- `showLocalModelsModal` - Local models modal

**Other:**
- `showShortcuts` - Keyboard shortcuts
- `showArchivedChats` - Show archived chats toggle
- `showChangelog` - Release notes/changelog

**Status**: These are UI state (not disabled features) - all become visible when users interact with controls.

---

## 3. CHAT FEATURE TOGGLES (Dynamic per-model)
In [src/lib/components/chat/Chat.svelte](src/lib/components/chat/Chat.svelte):

All initialized FALSE, toggled based on model capabilities:
- `imageGenerationEnabled` (line 160)
- `webSearchEnabled` (line 161)
- `codeInterpreterEnabled` (line 162)
- `codeExecutionEnabled` (line 163)
- `stableDiffusionEnabled` (line 164)
- `thinkingEnabled` (line 168, DEFAULT: true)

Control logic (lines 543-573):
- Only enabled if `$config.features?.enable_*` is true
- AND model includes feature in `meta.defaultFeatureIds`
- Example: `webSearchEnabled = model.info.meta.defaultFeatureIds.includes('web_search')`

---

## 4. REASONING TOGGLE (Model-Specific)
[src/lib/constants.ts](src/lib/constants.ts#L109): `toggle_reasoning: false`

In [src/lib/components/chat/MessageInput.svelte](src/lib/components/chat/MessageInput.svelte#L564):
```svelte
let showThinkingButton = false;
$: showThinkingButton = 
  model && 
  ($models.find((m) => m.id === model)?.info?.meta?.capabilities?.toggle_reasoning ?? false)
```
- **Control**: Reasoning button shown only if:
  1. Model has `meta.capabilities.toggle_reasoning === true` 
  2. Otherwise defaults to false
- **UI**: Thinking dropdown menu (lines 1750, 2101) - users can toggle thinking on/off

---

## 5. MODEL METADATA HIDDEN STATE
[src/lib/components/workspace/Models/ModelMenu.svelte](src/lib/components/workspace/Models/ModelMenu.svelte#L89):
```svelte
{#if model?.meta?.hidden ?? false}
  <!-- Hidden model indicator -->
{/if}
```
- **Pattern**: Models can have `meta.hidden = true` property
- **Effect**: Marks model as hidden (visual indicator in UI)
- **Usage**: Filter hidden models in admin [src/lib/components/admin/Evaluations/Leaderboard.svelte](src/lib/components/admin/Evaluations/Leaderboard.svelte#L51): `!m?.info?.meta?.hidden`

---

## 6. STATUS HISTORY HIDDEN FLAG
[src/lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte](src/lib/components/chat/Messages/ResponseMessage/StatusHistory.svelte#L33):
```svelte
{#if status?.hidden !== true}
  <!-- Show status item -->
{/if}
```
- **Control**: Individual status items can be marked `hidden: true`
- **Effect**: Status history UI hides that specific status item
- **Usage**: In [src/lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte](src/lib/components/chat/Messages/ResponseMessage/StatusHistory/StatusItem.svelte#L22)

---

## 7. DISABLED WRITE ACCESS (Permission-Based UI Disabling)
[src/lib/components/workspace/Skills/SkillEditor.svelte](src/lib/components/workspace/Skills/SkillEditor.svelte#L20):
```svelte
export let disabled = false;
// disabled = !_skill.write_access ?? true;
```
Similarly in [src/lib/components/workspace/Prompts/PromptEditor.svelte](src/lib/components/workspace/Prompts/PromptEditor.svelte#L36)

- **Pattern**: Components disabled if `!write_access`
- **Effect**: 
  - Editor form fields become read-only
  - Submit buttons hidden (lines 167, 253)
  - Conditionals: `{#if !disabled}` sections hidden

---

## 8. PERMISSION SYSTEM (DEFAULT_PERMISSIONS)
[src/lib/constants/permissions.ts](src/lib/constants/permissions.ts) - All default FALSE except chat ops:

**Workspace (default false):**
- models, knowledge, prompts, tools, skills
- models_import, models_export
- prompts_import, prompts_export  
- tools_import, tools_export

**Sharing (default false):**
- models, public_models, knowledge, public_knowledge
- prompts, public_prompts, tools, public_tools
- skills, public_skills, notes, public_notes

**Features (default false - unless parent feature enabled):**
- api_keys, direct_tool_servers
- notes, channels, folders (default true in features)
- web_search, image_generation, code_interpreter (default true in features)
- memories (default true)

**Impact**: Entire workspace tabs hidden when permissions are false.

---

## 9. COMPONENTS WITH DISABLED STATE CONDITIONALS
Patterns showing UI disabled/hidden based on conditions:

**Skills [src/lib/components/workspace/Skills/SkillEditor.svelte](src/lib/components/workspace/Skills/SkillEditor.svelte):**
- Lines 235-253: Content area shows disabled overlay if `{#if disabled}`
- Line 161: Form fields bind `:disabled={disabled}`
- Line 167: Save button hidden `{#if !disabled}`

**Prompts [src/lib/components/workspace/Prompts/PromptEditor.svelte](src/lib/components/workspace/Prompts/PromptEditor.svelte):**
- Same pattern as Skills

**Notes [src/lib/components/notes/NoteEditor.svelte](src/lib/components/notes/NoteEditor.svelte#L115):**
- TODO comment: "pages: [] - TODO: Implement pages for notes" (not in use/planned)
- Lines 1004, 1015: Editor controls disabled based on `editor.can().undo()/redo()`

---

## 10. FALSE POSITIVES (NOT Actually Disabled)
These are normal state management, not permanently disabled features:

- `let loaded = false` - Async loading flags (everywhere)
- `let showConfirm = false` - Modal state toggles
- `let generating = false` - Request state flags
- `disabled={loading}` - Temporary disable during submission
- CSS classes: `.hidden`, `.opacity-0` - Responsive visibility (not feature disable)
- `draggable="false"` - HTML attributes for UX
- Modal `bind:show` - Modal visibility bindings (all temporary)

---

## SUMMARY TABLE

| Feature | Location | Status | Gating | Impact |
|---------|----------|--------|--------|--------|
| Notes | [notes/+layout.svelte](src/routes/\(app\)/notes/+layout.svelte#L13) | Default OFF | config flag | Workspace tab hidden |
| Direct Connections | [Chat.svelte](src/lib/components/chat/Chat.svelte#L463) | Default OFF | config flag | Model connection UI hidden |
| Community Sharing | [Tools.svelte](src/lib/components/workspace/Tools.svelte#L493) | Default OFF | config flag | Share buttons hidden |
| Admin Analytics | [admin/analytics](src/routes/\(app\)/admin/analytics/+page.svelte#L14) | Default ON | config flag | Page 404s when disabled |
| Reasoning Toggle | [MessageInput.svelte](src/lib/components/chat/MessageInput.svelte#L564) | Model-specific | model capability | Thinking button hidden |
| API Keys | [Account.svelte](src/lib/components/chat/Settings/Account.svelte#L255) | Default OFF | config flag + permission | Settings section hidden |
| Skills/Prompts Edit | [SkillEditor.svelte](src/lib/components/workspace/Skills/SkillEditor.svelte#L20) | Dynamic | write_access perm | Form fields disabled |
| Workspace Tabs | Various admin | Default OFF | permissions | Entire tabs hidden |

---

## TRULY NOT IN USE (Commented/TODO)
- **Pages in Notes** [src/lib/components/notes/NoteEditor.svelte](src/lib/components/notes/NoteEditor.svelte#L115)
  - Commented: `// pages: [], // TODO: Implement pages for notes`
  - Status: Planned feature, code scaffold present
  
- **File handling in Note chat** [src/lib/components/notes/NoteEditor/Chat.svelte](src/lib/components/notes/NoteEditor/Chat.svelte#L191)
  - Commented: `// ...(files && files.length > 0 ? { files } : {}) // TODO: Decide...`
  - Status: Decision pending

- **Filter order in Models** [src/lib/components/workspace/Models/FiltersSelector.svelte](src/lib/components/workspace/Models/FiltersSelector.svelte#L31)
  - Commented: `<!-- TODO: Filter order matters -->`
  - Status: Feature incomplete
