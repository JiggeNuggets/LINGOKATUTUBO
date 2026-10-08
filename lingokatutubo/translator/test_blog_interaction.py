from pathlib import Path

from django.test import SimpleTestCase


class BlogChapterInteractionContractTests(SimpleTestCase):
    """Regression coverage for the public editorial chapter engine only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        root = Path(__file__).resolve().parents[1]
        cls.script = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")
        cls.stylesheet = (root / "static" / "css" / "styles.css").read_text(encoding="utf-8")

    def _chapter_engine(self):
        start = self.script.index("  function initEditorialChapterSystem(rail) {")
        end = self.script.index("\n  function initEditorialChapterSystems()", start)
        return self.script[start:end]

    def test_chapter_state_is_shared_and_never_scrolls_to_the_rail(self):
        engine = self._chapter_engine()

        self.assertIn("function goToChapter(index, source)", engine)
        self.assertNotIn("scrollIntoView", engine)
        self.assertNotIn("location.hash", engine)
        self.assertNotIn("history.pushState", engine)
        self.assertIn("keepStoryViewportSteady(previousTop, previousScrollY)", engine)
        self.assertIn("window.scrollTo({ top: previousScrollY, behavior: \"auto\" })", engine)

    def test_active_sticky_link_only_scrolls_its_own_horizontal_container(self):
        engine = self._chapter_engine()

        self.assertIn("nav.scrollTo({", engine)
        self.assertIn("left: Math.min(maxLeft, Math.max(0, desiredLeft))", engine)
        self.assertNotIn("link.scrollIntoView", engine)

    def test_gestures_are_scoped_and_preserve_vertical_scroll(self):
        engine = self._chapter_engine()

        self.assertIn('track.addEventListener("wheel"', engine)
        self.assertNotIn('rail.addEventListener(\n        "wheel"', engine)
        self.assertIn("absX <= absY * 1.4", engine)
        self.assertIn("Math.abs(accumulatedDeltaX) < 70", engine)
        self.assertIn("}, 650)", engine)
        self.assertIn("pointerType !== \"touch\"", engine)
        self.assertIn("Math.abs(diffX) <= Math.abs(diffY) * 1.3", engine)
        self.assertNotIn("preventDefault()", engine[engine.index('track.addEventListener("wheel"'):])

    def test_editorial_overflow_and_touch_rules_are_scoped_to_public_blog(self):
        editorial_rules = self.stylesheet.rsplit(".editorial-page {", 1)[1].split("}", 1)[0]
        track_rules = self.stylesheet.split(".story-rail__track {", 1)[1].split("}", 1)[0]

        self.assertIn("overflow-x: clip", editorial_rules)
        self.assertIn("overflow: clip", track_rules)
        self.assertIn("touch-action: pan-y pinch-zoom", track_rules)
        self.assertIn("overflow-anchor: none", self.stylesheet)
