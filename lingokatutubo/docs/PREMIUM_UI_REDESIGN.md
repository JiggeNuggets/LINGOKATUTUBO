# Premium UI Redesign

## Previous visual problems

The existing interface had useful functional foundations, but the public experience was overly card-led, visually flat, and dependent on warm-paper and white surfaces. The hero did not establish a strong visual editorial identity, document-workflow panels had inconsistent density, and older CSS layers created competing component treatments.

## Design direction

The redesign treats LingoKatutubo as one connected product: a source-conscious cultural-learning publication and a practical bilingual document workspace. Public pages now use editorial composition, deep-forest contrast, restrained soft-green surfaces, image-ready media components, and a more intentional reading rhythm. Authenticated pages retain a compact, task-focused workspace feel.

## Component changes

- A consistent header, accessible Explore dropdown, and structured footer connect public and authenticated routes.
- Homepage sections use a two-column editorial hero, featured-story area, image-led Explore cards, a magazine-like Culture composition, a landscape-ready Nature feature, and a document-translation showcase.
- Document pages share refined panels, compact document cards, status treatments, empty states, workspace metrics, and review controls.
- Translation terminal states remain centered and preserve the required success action: `CHECK`.
- The existing owner-protected Bilingual Preview remains the review destination; no duplicate preview route was added.

## Colors, typography, and spacing

The approved forest, soft-green, amber, warm-paper, ink, muted, border, error, and info colors remain the source system. They are now balanced across white, warm-paper, soft-green, and deep-forest surfaces instead of repeating the same light card treatment. Display typography is reserved for editorial headlines; sans-serif remains for navigation, controls, metadata, and document interfaces.

Shared sizing tokens define normal, wide, and reading widths; desktop gutters; section rhythm; control height; radii; shadows; layering; and motion duration. This makes page density more consistent while keeping the Bilingual Preview appropriately wide.

## Buttons and cards

Primary buttons use forest green with a restrained hover lift and shadow. Secondary buttons use a light surface with a green border and text. Text links retain a clear hierarchy, and destructive styling remains reserved for removal. Editorial cards, feature cards, document cards, and workflow panels each have distinct roles instead of relying on one generic white-card pattern.

## Image strategy and attribution

No external or AI-generated cultural/documentary photography was added. The redesign uses the existing project-owned LingoKatutubo logo and neutral, image-ready editorial media surfaces. Published photography is explicitly prepared to carry a caption, source, photographer, license, and alt text. A reusable gallery is ready for verified `gallery_items`, with thumbnail selection, next/previous controls, a keyboard-accessible native-dialog lightbox, and source credit. This avoids unsupported cultural claims or false attribution while leaving a high-quality visual structure ready for verified media.

## Interaction and responsive behavior

The Explore dropdown has deliberate open, outside-click, and Escape-key behavior. Public cards and arrows use restrained hover motion; public sections use native IntersectionObserver reveal enhancement, with a no-animation fallback. Desktop uses editorial grids, tablet recomposes complex areas, and mobile moves hero and feature layouts to a single clear column with touch-friendly controls and compact document rows.

## Accessibility and performance

Semantic landmarks, labelled controls, focus states, owner-protected routes, secure logout, status messaging, and the existing exact `CHECK` flow are retained. Reduced-motion rules disable nonessential movement. The project-owned logo and document thumbnails use asynchronous decoding, and thumbnails / preview images use lazy loading where appropriate. No additional frontend framework or image library was introduced.

## Remaining limitations

Browser automation was unavailable during this pass, so live viewport verification is pending. Real cultural or landscape photography and verified source metadata should be supplied before rendering gallery items. Legacy CSS remains where it supports existing routes; clearly orphaned prototype hero and text-mark rules were removed, while the new premium layer overrides and unifies normal-user presentation without changing translation, OCR, datasets, authentication, ownership, or Translation Resources behavior.
