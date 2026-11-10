# GigBid design guide

Borrowed from the signed-in app of **Hikmah** (my FYP): `client/src/styles/tokens.css`.
GigBid is a working tool (inbox, editor, board), so it takes Hikmah's *app* system,
not its 3D-book landing page.

**Feeling:** a quiet, serious ledger. Paper by day, ink-black by night. One accent
colour. No gradients, no glows, no bouncing. The data (fit, risk, price) is the star.

## Colours (stored as "R G B" so Tailwind opacity like `bg-accent/10` works)

| Token | Light (parchment) | Dark (ink) | Used for |
|---|---|---|---|
| `--bg` | `244 240 229` #F4F0E5 | `10 10 10` #0A0A0A | page background |
| `--bg-sunk` | `236 231 217` | `5 5 5` | table headers, wells |
| `--surface` | `251 249 243` | `18 18 18` | panels |
| `--border` | `222 214 196` | `38 38 38` | hairlines |
| `--border-strong` | `201 190 166` | `51 51 51` | lines that must be seen |
| `--text` | `26 23 16` | `245 245 245` | main text |
| `--text-2` | `90 83 68` | `161 161 161` | body / secondary |
| `--text-3` | `110 102 86` | `115 115 115` | metadata |
| `--accent` | `122 93 21` brass | `16 185 129` emerald | buttons, links, focus |
| `--text-on-accent` | `251 249 243` | `10 10 10` | text on accent buttons |
| `--success` | `74 110 64` sage | `52 211 153` | "bid", supported claim |
| `--warning` | `160 90 20` ochre | `251 191 36` | "watch", partly supported |
| `--danger` | `156 74 34` vermilion | `248 113 113` | scam, blocked, unsupported |
| `--info` | `46 110 122` teal | `96 165 250` | neutral info, running node |

**Polarity rule:** brass is dark on paper (light text on it), emerald is bright on black
(dark text on it). Never white text on a bright accent.

## Type

- **Display / headings:** Spectral (serif), weight 300-400. Page titles only.
- **UI / body:** system-ui. Everything you read and click.
- **Data:** IBM Plex Mono, for numbers a person reads as data: prices, fit %, Connects,
  latency, ids. Small uppercase mono "eyebrow" labels with letter-spacing above a section
  (e.g. `FIT 0.82 · RISK LOW`).

## Shapes and depth

- Corners: 4px (`rounded-sm`). No pills except tiny status dots.
- Panels: 1px hairline border on `--surface`. No drop shadows (a shadow only means a
  sheet on top of a sheet: modals).
- A **2px accent bar on top** of the one panel that matters most on a screen (like
  Hikmah's "continue" card).
- **Segmented bars** (Hikmah's progress bar) for scores: fit score = 5 segments.

## Components

- **Primary button:** accent fill, `--text-on-accent` label, 4px corners.
- **Secondary button:** surface fill, accent text, `--border-strong` outline.
- **Badge:** mono, small, coloured text on a 10% wash of the same colour.
- **Evidence hover:** claim gets a dotted underline in success / warning / danger;
  hover shows the evidence item in a small panel.
- **Banner** (degraded mode): full-width, danger wash, one sentence + "retrying".

## Do / Don't

- Do: sentence case everywhere ("Approve and send", not "APPROVE AND SEND").
- Do: clear empty, loading and error states on every screen.
- Do: both themes; respect `prefers-color-scheme` with a manual toggle.
- Don't: gradients, glows, emoji icons, card-in-card-in-card, spinners for long runs
  (show the node timeline instead).
