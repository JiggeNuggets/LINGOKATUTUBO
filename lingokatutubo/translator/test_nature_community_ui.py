from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class NatureAndCommunityPresentationTests(TestCase):
    def test_public_editorial_pages_expose_page_scoped_presentation_hook(self):
        for route_name, page_key in (
            ("translator:nature", "nature"),
            ("translator:community", "community"),
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'data-editorial-page="{page_key}"', html=False)

    def test_visual_upgrade_is_limited_to_nature_and_community_selectors(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "styles.css").read_text(
            encoding="utf-8"
        )

        for selector in (
            '[data-editorial-page="nature"] .editorial-hero',
            '[data-editorial-page="community"] .editorial-hero',
            '[data-editorial-page="nature"] .story-slide:not(:has(.story-slide__media)).is-active',
            '[data-editorial-page="community"] #section-folk-speech .story-slide__study-figure-list',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)

        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)
        self.assertNotIn('[data-editorial-page="bagobo_tagabawa"]', stylesheet)
        self.assertNotIn('[data-editorial-page="culture"]', stylesheet)

    def test_nature_identity_refinements_remain_page_scoped(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "styles.css").read_text(
            encoding="utf-8"
        )

        for selector in (
            '[data-editorial-page="nature"] #section-foothill-ecology .story-slide__body',
            '[data-editorial-page="nature"] #section-agroforestry .story-slide__facts',
            '[data-editorial-page="nature"] #section-ancestral-stewardship .contemporary-practices__heading',
            '[data-editorial-page="nature"] .source-bibliography-item',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)

    def test_community_identity_refinements_remain_page_scoped(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "styles.css").read_text(
            encoding="utf-8"
        )

        for selector in (
            '[data-editorial-page="community"] .editorial-hero__title',
            '[data-editorial-page="community"] #section-community-education .story-slide__facts',
            '[data-editorial-page="community"] #section-learning-materials .story-slide__facts',
            '[data-editorial-page="community"] .editorial-page__sources',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)

    def test_category_mobile_refinements_remain_page_scoped(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "styles.css").read_text(
            encoding="utf-8"
        )

        for selector in (
            '[data-editorial-page="nature"] .sticky-story-nav',
            '[data-editorial-page="community"] .sticky-story-nav',
            '[data-editorial-page="nature"] .source-biblio-link',
            '[data-editorial-page="community"] .continue-card',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)

    def test_category_microinteractions_remain_scoped_and_announce_chapter_titles(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "styles.css").read_text(
            encoding="utf-8"
        )
        script = (Path(__file__).resolve().parents[1] / "static" / "js" / "app.js").read_text(encoding="utf-8")

        for selector in (
            '[data-editorial-page="nature"] .story-rail__button[data-story-prev]:hover:not(:disabled)',
            '[data-editorial-page="community"] .story-rail__dot:hover:not(.is-active)',
            '[data-editorial-page="nature"] .source-biblio-link:hover',
            '[data-editorial-page="community"] .sticky-story-nav__link:focus-visible',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, stylesheet)

        self.assertIn('const chapterTitle = activeSlide.querySelector("h2")?.textContent?.trim();', script)
        self.assertIn('Chapter ${index + 1} of ${slides.length}: ${chapterTitle ||', script)

    def test_nature_rail_derives_its_visible_chapter_count(self):
        body = self.client.get(reverse("translator:nature")).content.decode("utf-8")
        rail_template = (
            Path(__file__).resolve().parents[1]
            / "translator"
            / "templates"
            / "translator"
            / "partials"
            / "_story_rail.html"
        ).read_text(encoding="utf-8")

        self.assertIn("Explore 4 perspectives", body)
        self.assertNotIn("Explore six perspectives", body)
        self.assertIn("{{ sections|length }} perspectives", rail_template)

    def test_community_study_figures_are_semantic_and_keep_existing_claims(self):
        body = self.client.get(reverse("translator:community")).content.decode("utf-8")

        for text in ("90", "Proverbs", "97", "Riddles", "Figures from the documented study"):
            with self.subTest(text=text):
                self.assertIn(text, body)
        self.assertIn('class="story-slide__study-figures"', body)
        self.assertNotIn('id="section-gallery"', body)

    def test_existing_shared_chapter_contract_remains_available_on_both_pages(self):
        for route_name in ("translator:nature", "translator:community"):
            with self.subTest(route_name=route_name):
                body = self.client.get(reverse(route_name)).content.decode("utf-8")
                for marker in ("data-story-rail", "data-story-prev", "data-story-next", "data-story-dots", "data-sticky-nav"):
                    self.assertIn(marker, body)
