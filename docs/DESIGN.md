# Prophet Design Context

## Product

Prophet is a local-first desktop workbench for evidence-backed profiles, chat export and analysis, and reproducible fortune-method records. The interface should feel quiet, trustworthy, and tool-like rather than promotional.

## Confirmed direction

- Preserve the established Streamlit-era layout and visual identity while moving to a native `pywebview` shell.
- Support both light and dark system themes. Light mode is the primary reference.
- Keep the left navigation, large editorial hero, neutral controls, restrained cards, and purple selected state.
- Use the same visual system across all four routes; do not introduce route-specific redesigns.

## Tokens

| Role | Light | Dark |
|---|---|---|
| Canvas / paper | `#ffffff` | `#080808` / `#171717` |
| Primary text | `#080808` | `#f7f7f7` |
| Body text | `#363636` | `#d8d8d8` |
| Muted text | `#898989` | `#ababab` |
| Border | `#d8d8d8` | `#353535` |
| Selected row | `#f0ebff` | `#261f36` |
| Control | `#f5f5f5` | `#202020` |
| Control hover | `#ebebeb` | `#2b2b2b` |
| Focus / active | `#3b89ff` / `#7a3dff` | same |

The hero accent is a five-part line: purple, pink, blue, orange, green. Corners are mostly 4px for controls and 8px for cards.

## Layout

- Sidebar: approximately 21% of the window, bounded to 210–250px on desktop.
- Content: centered, maximum width 1180px, with generous top space.
- Hero: paper surface, 32px padding, large title, short description, 6px accent line at the bottom.
- Workflows: one main column, matching the former Streamlit reading order.
- Dense subviews may use local grids, but should collapse cleanly on narrow windows.

## Motion

- CSS only; no motion dependency.
- Hero settles by 12px and the accent line draws from left to right.
- Startup uses only the Prophet mark and name: it settles by 16px, holds for about two seconds, then the cover fades away.
- Controls use subtle 140–220ms hover feedback.
- Respect `prefers-reduced-motion` and remove decorative animation.

## Page classification

- Primary archetype: desktop workbench / B-end tool.
- Secondary archetype: reading and results workspace.
- Density: medium; confidence: high.
- Reference fidelity: preserve the original single-column task flow and use the Webflow reference for proportion, typography, surface treatment, and motion rather than changing the information architecture.

## Guardrails

- Do not reintroduce the rejected blue-gradient dashboard style.
- Do not change business behavior to achieve a visual effect.
- Keep privacy and local-storage boundaries explicit.
- Reuse native HTML controls and the existing component classes before adding new UI machinery.
