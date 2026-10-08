# Premium UI Redesign Audit

## Scope and guardrails

This audit covers the Django-rendered public, authenticated, and document-review interfaces in `translator/templates`, shared styles in `static/css/styles.css`, and progressive enhancement in `static/js/app.js`. Translation, OCR, job processing, ownership, authentication, datasets, and Translation Resources are out of scope.

## Current visual weaknesses

- Public pages use the same light card treatment for hero, feature, and workspace content, reducing hierarchy and making the homepage read like a prototype.
- The former homepage hero used a text-only wordmark block rather than an image-ready editorial media composition.
- Warm-paper and white surfaces are overused without enough deep-forest or soft-green contrast to distinguish content types.
- Cards vary between compact document rows, panels, metric cards, and resource tables with uneven padding, radius, and hover treatment.
- Buttons are functional but their heights, text emphasis, and action hierarchy differ across document, dashboard, and preview pages.
- The shared stylesheet contains legacy and phase-specific rules in several locations, so the same component has multiple successive overrides.
- Explore navigation previously depended on native disclosure markup and needed a custom, explicitly hidden dropdown implementation to avoid inline-menu and duplicate-chevron failures.
- Existing responsive rules collapse grids correctly in many places, but public editorial layouts had no deliberate desktop/tablet/mobile composition.
- The footer was minimal and did not expose the site’s cultural-learning and translation purposes.
- Several current UI strings use text arrows and inconsistent icon treatments; new public components should use controlled CSS/SVG iconography.

## Components to standardize

1. Shared page widths and gutters: normal, reading, and wide document-preview containers.
2. Button hierarchy: primary, secondary, text/tertiary, and existing danger-only destructive actions.
3. Surfaces: editorial media cards, lightweight feature cards, compact document cards, and document-review workspace panels.
4. Section headings: restrained eyebrow, editorial heading, and supporting copy.
5. Status indicators: existing compact completed, processing, failed, and warning badges.
6. Header/footer: consistent navigation, dropdown, mobile accordion, source-aware editorial footer.
7. Motion: small hover, reveal, and dropdown transitions with `prefers-reduced-motion` support.

## Accessibility and responsive considerations

- Maintain visible focus, semantic buttons/links, labels, status announcements, owner-scoped routes, and secure POST logout.
- Preserve the existing centered translating/terminal overlays and the exact `CHECK` label.
- Keep document interfaces information-dense but compact, with controls at touch-friendly sizes.
- Use CSS-only neutral media compositions and the existing project-owned logo until verified documentary photography, attribution, and licenses are available.
- Test public and authenticated layouts at 1440, 1280, 1024, 768, 390, and 360 pixels when browser automation is available.

## Redesign direction

The redesign uses editorial composition, deliberate surface contrast, a strengthened type scale, restrained shadows, and image-ready media components. It does not add unverified cultural content, decorative motifs, or external imagery.
