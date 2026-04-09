# UI Style Notes Run 01

## Core design tokens or style rules applied
The base CSS variables were unified. Primary color variables include:
- `--cems-primary`: `#6B0F1A` (Deep Maroon Base)
- `--cems-primary-light`: `#A11217` (Rich Crimson)
- `--cems-primary-dark`: `#4A0B12` (Dark Red for states)
- `--cems-accent`: `#F2A900` (Warm Gold/Amber highlight)
- `--cems-bg`: `#F8F9FB` (Light Neutral Background)

## Exact or approximate palette used from the logo
The palette was directly inspired by the Campus Student Council logo's fire and eagle colors (deep reds/maroons mixed with striking yellow and gold accents). The branding identity moves decidedly away from startup blue or overly rounded tech aesthetics to a solid, academic, and authoritative red/white styling.

## Shared layout/component principles
- **Spacing:** Maintaining rhythmic vertical spacing with Tailwind-like rem steps (`0.75rem`, `0.5rem`).
- **Cards & Surfaces:** Clean white surfaces (`#FFFFFF`) with minimal gray borders (`#E5E7EB`) ensuring high contrast text (`#1F2937`).
- **Typography:** Retained the existing base sans-serif setup, standardizing colors.

## How admin and student pages were aligned visually
By configuring `.cems-primary` variables at the `:root` level in `cems.css`, both the admin panel files and student-facing ballot files immediately inherit this structure. Buttons across both spaces utilize these primary brand variables rather than one-off styles.

## Any reusable CSS/component strategy introduced
Leveraged strict CSS custom property definitions (`var(--cems-*)`) directly in `static/css/cems.css`. This prevents inline style bloat in Django templates and establishes a shared design system file across all apps.
