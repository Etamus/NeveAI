# Neve AI Streaming Fix v3 — Content Buffer System

## Root Cause
Svelte 5 proxy-based reactivity: `message.content += value` on proxied object triggers full reactive cascade per token (~50-100/sec). Previous RAF/debounce approaches only batched the `history.messages[id] = message` assignment but the proxy mutation on `message.content` already triggered updates.

## Fix: Plain JS Content Buffers
- `_contentBuffers = new Map()` accumulates streaming text in plain JS (not proxied)
- `_flushRAF` = requestAnimationFrame loop writes to proxy (~60fps, smooth visual updates)
- `chatCompletionEventHandler`: writes to buffer instead of `message.content += value`
- `chatEventHandler`: `chat:message:delta` also buffered + returns early
- `onHistoryChange`: skips entirely when `_flushInterval !== null`
- `getContents()` only called directly from done handler (artifacts after completion only)
- `activeChatIds` cleared immediately on done (fast spinner stop)

## Key Files
- Chat.svelte: buffer system, chatCompletionEventHandler, onHistoryChange
- ChatItem.svelte: spinner gradient `dark:from-gray-850`
- utils/index.ts: `getCodeBlockContents()` (expensive regex, now only runs once at completion)


## Code Block Layout Note
- Streaming code block bottom jitter can come from horizontal scrollbar height toggling as long lines appear; reserve it with `overflow-x-scroll` on the `<pre>` and keep `white-space: pre`/fixed line-height on a block `<code>`.
- Avoid `highlightAuto` while a code block is still streaming for unknown languages; autodetection can change markup/metrics repeatedly. Use explicit language highlighting or escaped plaintext until completion.
