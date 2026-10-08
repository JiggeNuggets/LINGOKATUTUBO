# Blog chapter UX stability audit

Scope: only the public editorial category pages `/bagobo-tagabawa/`, `/culture/`, `/nature/`, and `/community/`. Translator workflows, content claims, and the homepage were not changed.

## Audit and root cause

`_story_rail.html` supplies a single shared rail, track, Previous/Next controls, and dot controls. `_story_slide.html` supplies the in-flow active chapter. `editorial_page.html` supplies the sticky chapter navigation and reading progress. `initEditorialChapterSystem` in `static/js/app.js` is the one shared interaction engine.

Before this change, Previous, Next, dots, sticky links, Arrow keys, Home/End, and touch swipes called `showSlide(index, true)`. Its `true` path scheduled `rail.scrollIntoView({ block: "start" })`; this is the proven direct source of the vertical relocation. Active sticky links also used `link.scrollIntoView({ inline: "center", block: "nearest" })`, which could move the document while trying to reveal a narrow-screen nav item. Trackpad and edge clicks called the same function with `false`, so they avoided that first direct cause.

There was no `location.hash`, `window.location.hash`, `history.pushState`, or `history.replaceState` use in the chapter engine. Sticky links are hash anchors, but their in-story click handler prevents the default anchor navigation. Direct anchors such as `#interactive-experience`, `#section-gallery`, and `#section-sources` remain normal page links. The hero Explore action intentionally uses `scrollIntoView`; the Back-to-top control intentionally uses `window.scrollTo({top: 0})`; neither is chapter navigation. Gallery modal focus management is isolated to the gallery. No chapter switch calls `focus()`.

The previous slide transforms were only 16 px, but the track had `overflow: visible`; a transformed full-width slide therefore could contribute visual overflow. `body` already had a global horizontal overflow rule, but that is not the stability mechanism used here. The editorial root and contained experience/track now clip horizontal overflow locally.

## Research principles used

- The [W3C APG carousel pattern](https://www.w3.org/WAI/ARIA/apg/patterns/carousel/) calls for native Previous/Next controls, optional slide pickers, polite announcement for a non-rotating carousel, and no focus movement after using controls.
- The [W3C carousel tutorial](https://www.w3.org/WAI/tutorials/carousels/) requires keyboard operation, communicated changes, and understandable focus behavior.
- [MDN Pointer Events](https://developer.mozilla.org/en-US/docs/Web/API/Pointer_events) describes one input model for mouse, pen, and touch; [MDN `touch-action`](https://developer.mozilla.org/en-US/docs/Web/CSS/touch-action) documents delegating vertical pan and pinch zoom to the browser.
- [MDN `history.replaceState`](https://developer.mozilla.org/en-US/docs/Web/API/History/replaceState) supports non-navigation URL state if it is ever needed. It was deliberately not added: stable chapter state has no need to replace direct anchors.

## Implementation

`goToChapter(index, source)` is the only state-changing path used by controls, dots, sticky navigation, keyboard, trackpad, touch swipe, edge click, and the existing programmatic event. It updates the active chapter, counter, disabled buttons, dots, sticky `aria-current`, progress, hint, animation direction, and one polite live region.

The active sticky link is centered with `nav.scrollTo({ left })` on the sticky nav container only; document scrolling is never used for nav synchronization. The chapter transition stays inside `.story-rail__track`: outgoing content fades/slides 18 px out and the new content enters from 18 px over 320 ms. The track clips this transform.

Each change records the track’s viewport top and `window.scrollY`; an animation-frame guard restores the prior scroll position only if a layout or browser-anchor drift exceeds one pixel. It never scrolls to the rail or to the top. `.interactive-experience { overflow-anchor: none; }` prevents browser scroll anchoring from treating chapter-height changes as a reason to move the document.

Horizontal wheel handling is attached only to the track. It requires `abs(deltaX) > abs(deltaY) * 1.4`, aggregates at least 70 px in 180 ms, and applies a 650 ms one-change cooldown. It is passive and never prevents native vertical scrolling. Touch uses Pointer Events on the same track with `touch-action: pan-y pinch-zoom`, requires 48 px and a 1.3 horizontal-intent ratio, and ignores protected controls, images, galleries, links, forms, dialogs, and text selections. At boundaries `goToChapter` returns without moving the page or changing category.

The hint is session-scoped: it hides after the first successful chapter change. The live announcement is concise: `Chapter N of total: category`. Reduced-motion users receive no chapter animation and no smooth nav-scroll behavior.

Rejected approaches: document-level `scrollIntoView`, direct hash assignment, document-level wheel listeners, `touch-action: none`, fixed/max slide heights, and a page-wide transition.

## QA and current content inventory

Automated source and template checks cover the shared engine, contained nav scrolling, gesture thresholds/cooldown, protected targets, focus independence, and scoped clipping. `python manage.py check`, `python manage.py test translator.test_navigation_homepage translator.test_blog_interaction`, and `node --check static/js/app.js` pass (30 tests).

| Page | Actual verified chapter count | Shared system | Automated interaction contract | Live browser |
| --- | ---: | --- | --- | --- |
| Bagobo-Tagabawa | 6 | Yes | Pass | Not available in this environment |
| Culture | 4 | Yes | Pass | Not available in this environment |
| Nature | 4 | Yes | Pass | Not available in this environment |
| Community | 0 | Ready when verified sections exist | No chapter controls to exercise | Not available in this environment |

Community is currently intentionally content-empty in `translator/editorial_content.py` (`story_navigation` and `sections` are both empty). No chapters were invented or cultural content changed, so an honest Community chapter N → N+1 live transition is not possible until verified Community sections are supplied. The reusable template and engine automatically use the actual section count when they are present.

The in-app browser service reported no available browser, so no screenshots, physical two-finger trackpad run, touch-emulation run, responsive viewport captures, or measured `scrollY` values are claimed in this audit. The regression contract specifically locks in the mechanisms required for those checks: chapter changes do not call `scrollIntoView`, document state is restored on drift, and editorial clipping contains transform overflow. A browser measurement of `scrollWidth` remains outstanding.
