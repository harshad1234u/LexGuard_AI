---
name: LexGuard Intelligence
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#45464d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#0051d5'
  on-secondary: '#ffffff'
  secondary-container: '#316bf3'
  on-secondary-container: '#fefcff'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#002114'
  on-tertiary-container: '#069669'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#dbe1ff'
  secondary-fixed-dim: '#b4c5ff'
  on-secondary-fixed: '#00174b'
  on-secondary-fixed-variant: '#003ea8'
  tertiary-fixed: '#85f8c4'
  tertiary-fixed-dim: '#68dba9'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Hanken Grotesk
    fontSize: 40px
    fontWeight: '600'
    lineHeight: 48px
    letterSpacing: -0.025em
  headline-xl:
    fontFamily: Hanken Grotesk
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Hanken Grotesk
    fontSize: 26px
    fontWeight: '600'
    lineHeight: 34px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Hanken Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Hanken Grotesk
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Hanken Grotesk
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.02em
  citation-code:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: -0.01em
  citation-badge:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-sm: 1rem
  gutter-lg: 2rem
  margin: 1.5rem
  margin-sm: 1rem
  margin-lg: 2.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system embodies the rigor, precision, and authority of institutional legal practice fused with the fluid speed of modern AI systems. The tone is deeply restrained, cerebral, and unshakeable—avoiding both the cold impersonality of legacy compliance software and the hyperactive neon aesthetics of consumer tech startups.

### Design Principles
- **Evidentiary Precision:** Every data point, citation, and confidence score is anchored to an inspectable primary source. Nothing floats ambiguously; visual hierarchy mirrors evidentiary weight.
- **Calm Authority:** High-stakes legal workflows demand visual silence. Whitespace is generous, chromatic noise is strictly contained, and interactive states remain controlled and discreet.
- **Dual-Register Reading:** The system separates modern interface chrome (structured metrics, navigation, verification statuses) from substantive evidentiary content (statutes, contracts, judicial records, and clauses).

### Visual Movement
The system relies on **Modern Corporate Minimalism** accented with **Editorial Structure**: sharp 1px grid architecture, purposeful surface tints, crisp slate borders, and typographic distinction between metadata, analytical commentary, and raw legal text.

## Colors

The palette establishes an immediate aura of trust and institutional competence through rich midnight slates and resolute corporate blue, framed by warm, low-fatigue document surfaces.

### Semantic Palette & Roles
- **Primary Canvas (`#F8FAFC`):** Soft, non-glare off-white background preventing eye strain during multi-hour document discovery.
- **Surface Elevation 0 (`#FFFFFF`):** High-clarity white for active panels, document viewing areas, cards, and modal dialogs.
- **Surface Elevation 1 (`#F1F5F9`):** Neutral foundation for sidebars, inspector viewports, and audit rail backdrops.
- **Primary Ink (`#0F172A`):** Deep Midnight Slate for high-priority headings, primary interface buttons, and active tab indicators.
- **Secondary Ink (`#334155`):** Muted slate for substantive legal body copy and synthesis text.
- **Tertiary Ink / Subtext (`#64748B`):** Structural labels, table headers, metadata captions, and disabled states.
- **Structural Borders (`#E2E8F0` / `#CBD5E1`):** Precision 1px dividers isolating analytical zones without visual friction.

### Evidentiary & Verification System
Status states must never scream; they inform with surgical clarity:
- **Verified / Supported:** Emerald Base (`#059669`), Surface Tint (`#ECFDF5`), Border Accent (`#A7F3D0`). Used for affirmed citations, matched precedents, and cross-referenced clauses.
- **Review Required / Partial Support:** Amber Base (`#D97706`), Surface Tint (`#FFFBEB`), Border Accent (`#FDE68A`). Signals conflicting clause interpretations, missing exhibits, or low confidence bounds.
- **Flagged / Rejected:** Rose Base (`#E11D48`), Surface Tint (`#FFF1F2`), Border Accent (`#FECDD3`). Flags explicit contractual breaches, jurisdictional disqualifications, or contradicted testimony.
- **Informational / Precedent Context:** Cobalt Base (`#2563EB`), Surface Tint (`#EFF6FF`), Border Accent (`#BFDBFE`). Denotes statutory references, cross-references, and systemic insights.

## Typography

The typography strategy builds deliberate boundaries between structural guidance, content synthesis, and mechanical legal citations.

### Font Pairings & Application
- **Hanken Grotesk (Headlines):** Contemporary, chiseled grotesque with architectural clarity. Used for primary views, page headings, dossier titles, and section splits.
- **Inter (Body & Controls):** Maximum legibility at small-to-medium text sizes. Neutral and balanced, handling legal rationale, commentary, summaries, table data, and form fields without visual distraction.
- **JetBrains Mono (Metadata & Technical Anchors):** Strictly designated for docket references, Bates stamps, page indices, section tokens (e.g., `§ 12.4(a)`), cryptographic checksums, and model confidence percentages.

### Content Conventions
When primary legal contract source excerpts are rendered within document viewer frames or citation inspectors, they must maintain a dedicated typographic treatment: indented 12px with an inner `border-l-2` colored in `#CBD5E1`, set in `body-sm` with a slightly expanded line-height (`1.65`) for effortless scanning.

## Layout & Spacing

The layout philosophy follows a **Split-Plane Inspection Grid** engineered for side-by-side legal analysis, structured cross-referencing, and real-time document discovery.

### Grid & Breakpoints
- **Desktop (1440px and above):** Dual-workspace split. Left pane: Fixed-width or collapsible navigation (260px) + flexible working document canvas (flex-grow). Right pane: Dedicated AI analysis, risk radar, and evidentiary citation rail (420px fixed).
- **Laptop / Small Desktop (1024px – 1439px):** Inspector pane shifts to a tabbed sliding drawer (380px) or 50/50 comparison split when comparing active clauses against gold-standard playbooks.
- **Tablet (768px – 1023px):** Fluid single-column layout with pinned bottom sheet for legal risk evaluations and badge summaries.
- **Mobile (Below 768px):** Stacked full-width views. Complex review workflows default to executive summaries with expandable detail sheets.

### Spacing Rhythm
Vertical and horizontal rhythm strictly adheres to an 8px base grid, using `space-xs` (4px) for micro-alignments such as badge icon offsets, `space-sm` (8px) for related form-control gaps, `space-md` (16px) for interior card padding, and `space-lg` (24px) for structural section separation.

## Elevation & Depth

Visual hierarchy is communicated through **tonal layering and crisp micro-borders**, rather than heavy drop shadows. Legal professionals demand structured, reliable surfaces that feel stable and planar.

### Elevation Levels
- **Base Layer (Ground - #F8FAFC):** The foundational substrate of the application.
- **Layer 1 (Card & Section Enclosure - #FFFFFF):** Bounded by a razor-thin 1px border (`#E2E8F0`). Zero shadow or an imperceptible ambient trace: `0 1px 2px 0 rgba(15, 23, 42, 0.04)`.
- **Layer 2 (Interactive Flyouts & Floating Toolbars):** Precision flyouts, search dropdowns, and contextual snippet popovers use `#FFFFFF`, a 1px border (`#CBD5E1`), and a focused low-opacity shadow: `0 4px 12px -2px rgba(15, 23, 42, 0.08), 0 2px 4px -2px rgba(15, 23, 42, 0.04)`.
- **Layer 3 (Modals & Deep Focus Overlays):** Used for document ingestion setups, redline comparison audits, and bulk-tagging dialogs: `0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 8px 10px -6px rgba(15, 23, 42, 0.04)`. Backdrop filter applied: `rgba(15, 23, 42, 0.4)` with `backdrop-blur(4px)`.

### Border Integrity
Every structural interface split (sidebars, panels, inspection drawers) is separated by a 1px solid stroke (`#E2E8F0`). Borders take precedence over shadows to create clear functional demarcations.

## Shapes

The design system employs **Soft Structural Shapes (`roundedness: 1`)** to maintain enterprise credibility while mitigating visual rigidity.

### Radius Specifications
- **Controls & Form Elements (Buttons, Inputs, Selects):** `0.375rem` (6px) to `0.5rem` (8px). Delivers a crisp, tactile target without bubbly or playful aesthetics.
- **Cards, Panels, and Document Containers:** `0.5rem` (8px) on standard viewports; `0.75rem` (12px) for root-level dashboard modules and modal windows.
- **Badges, Tags, and Citation Chips:** `0.25rem` (4px) to `0.375rem` (6px). Compact and rectangular, preserving tabular alignment and avoiding circular or pill silhouettes.
- **Split Controls & Button Groups:** Flush internal borders with outer corner radii matching `0.375rem` (6px).

## Components

### Buttons & Actions
- **Primary Action:** Solid Midnight Slate (`#0F172A`) with pure white text (`#FFFFFF`). On hover: `#1E293B`. Active: `#020617`. Height: 36px (standard) / 40px (prominent). Padding: 12px 16px. Typography: `label-md`.
- **Brand / Accent Action:** Royal Slate Blue (`#2563EB`) with white text. Reserved for primary AI generation, compliance certification, and final sign-off triggers.
- **Secondary / Outline:** White background, 1px solid `#E2E8F0`, slate text (`#1E293B`). On hover: background `#F8FAFC`, border `#CBD5E1`.
- **Ghost Action:** Transparent background, muted slate text (`#475569`). On hover: background `#F1F5F9`, text `#0F172A`.

### Verification Badges & Citation Chips
- **Construct:** Built with an inline status indicator icon (12px), an uppercase or capitalized label (`label-sm`), and an optional monospace citation reference (`citation-badge`).
- **Styles:**
  - *Verified:* `#ECFDF5` background, `#059669` text, `#A7F3D0` border.
  - *Review Needed:* `#FFFBEB` background, `#D97706` text, `#FDE68A` border.
  - *Flagged / Non-Compliant:* `#FFF1F2` background, `#E11D48` text, `#FECDD3` border.
  - *Statute / Clause Pill:* `#F1F5F9` background, `#334155` text, `#E2E8F0` border, `font-family: JetBrains Mono`.

### Form Fields & Search Inputs
- **Base Input:** Background `#FFFFFF`, 1px solid border `#CBD5E1`, text `#0F172A`, placeholder `#94A3B8`.
- **Focus State:** 1px solid border `#2563EB`, with a clean 2px focus ring tinted in `rgba(37, 99, 235, 0.15)`. No dramatic expansions.
- **Integrated Add-ons:** Leading icon slot for search / filter triggers; trailing monospace shortcut hint (e.g., `⌘K`) set in `#64748B` with a subtle `#F1F5F9` badge.

### Dual-Column Inspection Cards
- **Structure:** Encapsulated in 1px `#E2E8F0` border, `#FFFFFF` background, rounded `8px`.
- **Header:** Features document metadata, Bates number, confidence rating, and expansion toggle on a subtle `#F8FAFC` top strip (36px height) with bottom border.
- **Content Area:** Two-column comparative view: Left side displays extracted primary legal text with highlight overlays; Right side renders AI synthesis, statutory matches, and cross-reference validation.

### Segmented Controls & Tabs
- **Tab Bars:** Non-pill, architectural underline style. Inactive tabs use `#64748B` with transparent bottom border. Active tab features `#0F172A` text with a 2px high `#0F172A` or `#2563EB` bottom bar.
- **Segmented Toggle Group:** `#F1F5F9` enclosed container (4px padding). Active toggle item has an elevated `#FFFFFF` surface with a subtle 1px border (`rgba(15, 23, 42, 0.08)`) and `#0F172A` text; inactive items have transparent backgrounds with `#64748B` text.

### Selection Controls (Checkboxes & Radios)
- **Checkboxes:** Crisp 16px square with 4px border radius. Unchecked: `#FFFFFF` with 1px border `#CBD5E1`. Checked: Solid `#0F172A` fill with white checkmark glyph.
- **Radio Buttons:** Crisp 16px circle. Selected: White interior circle enclosed by `#0F172A` ring (5px active dot).