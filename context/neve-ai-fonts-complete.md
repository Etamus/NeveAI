# Neve AI - Font Architecture (Complete)

## Font Files Available
Location: `/static/assets/fonts/`
- Archivo-Variable.ttf
- Geist-Variable.woff2
- GeistMono-Variable.woff2
- InstrumentSerif-Italic.ttf
- InstrumentSerif-Regular.ttf
- Inter-Variable.ttf
- Mona-Sans.woff2
- Vazirmatn-Variable.ttf

## @font-face Declarations
Location: `src/app.css` lines 3-20
- **Geist**: Geist-Variable.woff2 (woff2, weights 100-900, font-display: swap)
- **Geist Mono**: GeistMono-Variable.woff2 (woff2, weights 100-900, font-display: swap)
- **Vazirmatn**: Vazirmatn-Variable.ttf (font-display: swap)

## CSS Classes with Font Definitions
Location: `src/app.css`
- `.font-secondary`: 'Geist', sans-serif (line ~52)
- `.font-primary`: 'Geist', 'Vazirmatn', sans-serif (line ~155)
- `.input-prose`: 'Segoe UI', 'Vazirmatn', ui-sans-serif, system-ui, sans-serif (line ~95)
- `.markdown-prose`: 'Segoe UI', 'Vazirmatn', ui-sans-serif, system-ui, sans-serif (line ~120)
- `.markdown-prose-sm`: 'Segoe UI', 'Vazirmatn', ui-sans-serif, system-ui, sans-serif (line ~135)
- `.markdown-prose-xs`: 'Segoe UI', 'Vazirmatn', ui-sans-serif, system-ui, sans-serif (line ~145)
- `.markdown`: 'Segoe UI', 'Vazirmatn', ui-sans-serif, system-ui, sans-serif (line ~150)
- `.chat-user-content`: 'Segoe UI', 'Vazirmatn', ui-sans-serif, system-ui, sans-serif (line ~155)

## Segoe UI Usage Status
**YES - "Segoe UI" is already defined** as a system font fallback (not via @font-face)

## Font Preloading
Location: `src/app.html` lines 17-18
- `/assets/fonts/Geist-Variable.woff2` (as="font" type="font/woff2")
- `/assets/fonts/GeistMono-Variable.woff2` (as="font" type="font/woff2")

## Inline Font-Family in Svelte Components
- Suggestions.svelte (67, 78): 'Geist', sans-serif
- MessageInput.svelte (1951, 1964, 2036, 2048): 'Segoe UI', sans-serif
- MessageInput/IntegrationsMenu.svelte (124): 'Segoe UI', sans-serif
- MessageInput/InputMenu.svelte (155): 'Segoe UI', sans-serif
- FileNav/NotebookView.svelte (473, 534, 548, 563, 581, 618, 633): 'Segoe UI' (mono/sans-serif)
- FileNav/JsonTreeView.svelte (75): 'Geist Mono', monospace
- FileNav/FilePreview.svelte (573): 'Geist Mono', monospace

## Tailwind Configuration
Location: `tailwind.config.js`
- No explicit fontFamily theme extend
- Uses tailwind default typography plugin with @tailwindcss/typography
