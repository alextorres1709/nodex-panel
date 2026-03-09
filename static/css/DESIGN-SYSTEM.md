# NodexAI Panel — Design System

## Color Tokens

### Light Mode
- `--brand-primary`: #7c3aed (violet-600)
- `--brand-primary-light`: #8b5cf6 (violet-500)
- `--brand-primary-dark`: #6d28d9 (violet-700)

### Dark Mode
- `--brand-primary`: #22c55e (green-500)
- `--brand-primary-light`: #4ade80 (green-400)
- `--brand-primary-dark`: #16a34a (green-600)

### Semantic Colors (both modes)
- `--danger`: #ef4444
- `--warning`: #f59e0b
- `--success`: #059669
- `--info`: #3b82f6

## Typography
- Font: Inter (weights 300-900)
- Body: 14px / line-height 1.5
- Page titles: 24px / weight 700
- Section headers: 16px / weight 700
- Labels: 11px / weight 700 / uppercase

## Components
- Border radius: 8px (sm), 12px (md), 16px (lg), 20px (xl)
- Shadows: Minimal, single-layer, low opacity
- Badges: 6px radius, weight 600
- Buttons: Primary (filled, white text), Secondary (outlined, transparent bg)

## Client Project Customization

To adapt this design system for a client project:

1. Replace `--brand-*` values in `:root` with the client's light mode palette
2. Replace `--brand-*` values in `[data-theme="dark"]` with the client's dark mode palette
3. Search for hardcoded `rgba(124, 58, 237, ...)` and `rgba(34, 197, 94, ...)` values and update them
4. Replace logo assets in `/static/img/`
5. Update Chart.js color arrays in `getChartTheme()` in `app.js`
6. Update `.sidebar-logo` and `.login-logo` background colors if needed
