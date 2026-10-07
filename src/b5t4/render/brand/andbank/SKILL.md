---
name: andbank-brand
description: Use this skill whenever producing presentations (.pptx), slide decks, or any visual deliverable for Andbank. Also trigger when the user mentions Andbank corporate identity, brand colors, or asks for on-brand materials. This skill contains the full Andbank corporate identity guidelines — colors, typography, logo placement, slide layouts — extracted from their official Manual de Identidad Corporativa. Always consult this skill before creating any Andbank-branded output, even for quick one-off slides.
---

# Andbank Corporate Identity — Presentation & Brand Skill

This skill codifies the Andbank corporate identity guidelines for use when generating branded presentations and documents. All specifications come from the official *Manual de Identidad Corporativa*.

---

## 1. Brand Overview

**Company:** ANDBANK — Private Bankers  
**Tagline:** *Private Bankers* (set in Century Gothic Italic)  
**Founded:** 1930 (Andorra)  
**Brand tone:** Sober, distinguished, clean, generous use of white space.

---

## 2. Color Palette

### Primary Colors (use these for all core corporate / brand materials)

| Name | PANTONE | CMYK | RGB | HEX | Usage |
|---|---|---|---|---|---|
| **Andbank Red** | 485C | 0/96/100/0 | 213,43,30 | `#D52B1E` | Symbol (slash), tagline, accent highlights, red CTAs |
| **Black** | BLACK | 100/100/100/100 | 0,0,0 | `#000000` | Wordmark, body text on light backgrounds |
| **Andbank Warm Grey** | 403C | 18/22/26/49 | 146,139,129 | `#928B81` | Tagline (secondary mark), captions, subtle text, dividers |
| **50% Warm Grey** | 403C @ 50% | — | ~200,197,192 | `#C8C5C0` | Light backgrounds, secondary surfaces |

### Secondary Colors (for editorial, merchandising, advertising — never dominant)

| Name | PANTONE | RGB | HEX |
|---|---|---|---|
| Dark Burgundy | 7623C | 118,46,47 | `#762E2F` |
| Terracotta | 7625C | 193,80,65 | `#C15041` |
| Blush Pink | 488C | 220,177,164 | `#DCB1A4` |
| Deep Rose | 194C | 137,45,68 | `#892D44` |
| Bright Rose | 206C | 182,0,56 | `#B60038` |

### Tertiary Colors (extended palette for dense editorial — annual reports, magazines)

| Name | PANTONE | RGB | HEX |
|---|---|---|---|
| Dark Chocolate | 7532C | 100,80,60 | `#64513D` |
| Steel Blue | 7583C | 54,77,90 | `#364D5A` |
| Sage Green | 480C | 130,157,145 | `#7C978D` |
| 70% Warm Grey | 403C @ 70% | — | `#ADA8A0` |
| 40% Warm Grey | 403C @ 40% | — | `#D5D2CE` |

### Color Rules
- **Prioritise white space** — the brand identity should be surrounded by generous white.
- Primary colors for corporate / brand pieces; secondary for editorial accents only (never dominant).
- All primary and secondary colors can be combined freely, as long as identity essence is preserved.
- **Avoid blue and green backgrounds** — these are associated with competitor banks (especially in Andorra).
- On dark / saturated backgrounds, use the **white (negative)** version of the mark with red symbol, or fully white.

---

## 3. Typography

### Corporate Primary: **Myriad Pro**
The main typeface for ALL Andbank communications.

| Weight | Usage |
|---|---|
| **Light** | Body copy, large titles |
| **Regular** | Body copy, addresses, general text |
| **Semibold** | Subtitles, medium emphasis |
| **Bold** | Titles, key data, strong emphasis |
| **Condensed** variants | When space is tight |

**Editorial guidelines:**
- Body text: Light, Regular, or Medium weights only.
- Minimum 3pt gap between font size and leading (e.g., 11pt/14pt, 9pt/12pt).
- Recommended letter-spacing: 25 or higher for readability.
- Never use below 6pt.

### Tagline Font: **Century Gothic Italic**
Used ONLY for the tagline ("Private Bankers") within the imagotype and sub-brands.

### Digital Fallback: **Verdana**
For emails, internal digital docs, and contexts where Myriad Pro is unavailable.

### Advertising Typography Rules
- Titles in red (`#D52B1E`) for emphasis; body in dark grey/black.
- Product/service labels in UPPERCASE with heavier weight.
- Strong size contrast between title and body (≥15–20pt gap depending on weights).

### For PPTX generation (practical guidance)
Since Myriad Pro is a commercial Adobe font that may not be installed, use these fallbacks in python-pptx:
1. **First choice:** `Myriad Pro` (if available on the system)
2. **Fallback:** `Calibri` (visually closest widely-available sans-serif with humanist proportions)
3. **Tagline fallback:** `Century Gothic` → `Calibri Light Italic`

---

## 4. The Logo (Imagotype)

The Andbank imagotype consists of three elements:
1. **Wordmark** — "ANDBANK" in Luxury Platinum font (always use from digital master file)
2. **Symbol** — A red diagonal slash (73° angle) to the right of the wordmark
3. **Tagline** — "Private Bankers" in Century Gothic Italic, below the wordmark

### Placement Rules
- **Always position on the right side** of the format (top-right or bottom-right).
- Clear space (area of respect) = height of the letter "A" in the wordmark, on all sides.
- Minimum reproducible width with all elements: 40mm (472px). Below 40mm, the tagline disappears.
- Below 25mm, use wordmark + truncated symbol only. Absolute minimum: 15mm (177px).

### On Slides
- Logo goes **top-right or bottom-right**.
- On white/light backgrounds: use the **primary mark** (dark wordmark, red tagline & symbol).
- On dark/photographic backgrounds: use **white negative** version (white wordmark, red symbol, white tagline) or **full white monochrome**.
- On the corporate red background: use **full white** version.

---

## 5. Presentation (PowerPoint) Guidelines

From Section 09 of the brand manual:

### Slide Categories (standard template structure)
1. **Portada** (Cover) — Hero image with diagonal grey/white split, logo top-right or bottom-right
2. **Índice** (Index/TOC) — Clean grid layout, numbers in red
3. **Portadilla** (Section intro) — Large section number in warm grey, section title
4. **Marcador de capítulo** (Chapter marker) — Bold divider slide
5. **Titular + texto + contenido gráfico** — Title, body text, chart/image area
6. **Titular + texto** — Text-focused content slide
7. **Línea de tiempo** (Timeline)
8. **Tecnología** (Tech-themed slides)
9. **Diseño base + diagramas** — Charts, diagrams
10. **Diseño base para contenidos de texto** — Dense text layouts

### Slide Design Principles
- **Generous white space** — avoid cramming; split content across multiple slides.
- Logo always visible — typically small, top-right corner.
- Use the **diagonal motif** (the brand's signature angled line, derived from the symbol) as a graphic element on section dividers and covers.
- Charts and data visualizations should use the primary color palette: red for highlights/emphasis, warm grey for secondary data, black for labels.
- The red diagonal slash (symbol) can be used as a decorative/graphic element on dividers and editorial layouts, at varying scales — it does not need to maintain original proportions when used as a graphic motif.

### Slide Color Schemes

**Light slides (default):**
- Background: White (`#FFFFFF`)
- Title text: Black (`#000000`) or Warm Grey (`#928B81`)
- Body text: 60% Black or Warm Grey
- Accent: Red (`#D52B1E`)

**Dark slides (for impact/section dividers):**
- Background: Black (`#000000`) or Warm Grey (`#928B81`)
- Title text: White
- Accent: Red (`#D52B1E`)

**Red slides (for values/mission/emphasis):**
- Background: Red (`#D52B1E`)
- All text: White
- Can be used for brand statement or key message slides

### Practical PPTX Construction Notes
When building slides with python-pptx:
- Slide dimensions: Widescreen 16:9 (13.333" × 7.5" / 33.87cm × 19.05cm)
- Logo placement: right-aligned, top or bottom, with clear space equal to ≈ the "A" cap height
- Use `RGBColor(0xD5, 0x2B, 0x1E)` for red accents
- Use `RGBColor(0x92, 0x8B, 0x81)` for warm grey elements
- Use `RGBColor(0x00, 0x00, 0x00)` for titles/body on white
- Thin red lines (0.5–1pt) as separators/accents echo the symbol
- For data tables: clean lines, avoid heavy gridlines — use warm grey hairlines

---

## 6. Document Format Guidelines (general, applies to all outputs)

- **Brand mark always on the right** (top-right or bottom-right).
- Margins: 15mm minimum on all sides for print; 7mm absolute minimum for dense corporate docs.
- Footer area: reserved for logo + corporate info (web address in red `#D52B1E`, using Myriad Pro Bold).
- Web/URL always in lowercase, in red.
- The "motto" or web address must never exceed the cap-height of the tagline.

---

## 7. Quick Reference — Key Hex Codes

```
ANDBANK_RED       = "#D52B1E"
BLACK             = "#000000"
WARM_GREY         = "#928B81"
WARM_GREY_50      = "#C8C5C0"
WARM_GREY_70      = "#ADA8A0"
WARM_GREY_40      = "#D5D2CE"
WHITE             = "#FFFFFF"

# Secondary
DARK_BURGUNDY     = "#762E2F"
TERRACOTTA        = "#C15041"
BLUSH_PINK        = "#DCB1A4"
DEEP_ROSE         = "#892D44"
BRIGHT_ROSE       = "#B60038"

# Tertiary
DARK_CHOCOLATE    = "#64513D"
STEEL_BLUE        = "#364D5A"
SAGE_GREEN        = "#7C978D"
```
