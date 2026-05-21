# Neve AI - Key Patterns

## Build & Deploy
- `cd "d:\Neve AI" ; npm run build` then `Copy-Item -Path "d:\Neve AI\build\*" -Destination "d:\Neve AI\backend\open_webui\frontend" -Recurse -Force`
- After deploy, user must Ctrl+F5 to reload

## TipTap / ProseMirror
- `editor.getJSON()` returns ProseMirror document JSON with `{ type: "doc", content: [{ type: "paragraph", content: [...] }] }`
- `hardBreak` nodes represent Shift+Enter line breaks within a paragraph
- Multiple paragraphs = Enter key (or `editor.commands.enter()`)
- TurndownService converts HTML→markdown but trims trailing newlines - **unreliable for line detection**
- `eventDispatch('keydown')` in RichTextInput plugin returns before reaching `return false` catch-all for Shift+Enter - must dispatch BEFORE `return true`
- `content.md` for empty editor may be `""` or `"\n"` depending on trailing break conversion - never use prompt text to detect multiline

## Compact Input Bar
- `isInputMultiline` controls compact vs expanded
- Detection uses TWO methods:
  1. ProseMirror JSON (`content.json.content`): multiple paragraphs OR `hardBreak` node → structural multiline
  2. Height check (`tick().then()` → measure `<p>.getBoundingClientRect().height` vs `lineHeight`) → visual wrapping
- NEVER use `$: if (prompt === '')` reactive to reset isInputMultiline — TurndownService may output `""` for hardBreak-only content, causing the reactive to override the JSON check
- All reset logic must be in onChange: check if document is truly empty (`!nodes[0].content || nodes[0].content.length === 0`)

## ChatControls Panel
- `localStorage.chatControlsSize` stores stretched width in pixels
- `openPane()` reads localStorage to restore saved size
- PaneResizer must be shown for ALL panels (not conditional on specialPanel) — user wants horizontal drag always available


## Reasoning + Local Model Reload
- Para evitar vazamento de reasoning, sanitize sempre `output` antes de serializar/salvar (`sanitize_visible_output` em `backend/neveai/utils/middleware.py`) e remova marcadores de canal (`<|channel>thought`, `<|channel|>`, `<channel|>`).
- Preferência `Rápido/Raciocínio` deve persistir globalmente apenas quando todos os modelos selecionados suportam `toggle_reasoning`; modelos sem suporte devem forçar modo raciocínio.
- Para GGUF local, tratar mudança de predefinições como assinatura de carga: se assinatura atual divergir da assinatura salva, descarregar e carregar novamente antes do envio.
