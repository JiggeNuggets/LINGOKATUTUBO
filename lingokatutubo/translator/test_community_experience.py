from django.test import TestCase
from django.urls import reverse


class CommunityExperienceTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("translator:community"))
        self.body = self.response.content.decode("utf-8")

    def test_community_uses_three_verified_chapters_and_shared_rail(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(self.body.count('<article id="section-'), 3)
        self.assertIn('data-story-rail data-story-category="Community Life, Learning &amp; Continuity"', self.body)
        for label in ("Education", "Learning Materials", "Folk Speech"):
            self.assertIn(f">{label}</a>", self.body)
        for title in (
            "Community-Based Education in Astorga",
            "Learning Materials With Local Context",
            "Folk Speech in Scholarly Documentation",
        ):
            self.assertIn(title, self.body)

    def test_community_publishes_traceable_sources_and_no_unverified_gallery(self):
        self.assertIn("Sources and Further Reading", self.body)
        self.assertIn("Pangandoy Extension Program", self.body)
        self.assertIn("A study of Bagobo Tagabawa folk speech", self.body)
        self.assertNotIn('id="section-gallery"', self.body)
        self.assertNotIn("Traditional Inabal Weaving", self.body)

    def test_community_exposes_all_related_destinations(self):
        for path in ("/bagobo-tagabawa/", "/culture/", "/nature/", "/translate/"):
            with self.subTest(path=path):
                self.assertIn(f'href="{path}"', self.body)

    def test_community_keeps_shared_chapter_controls_and_accessibility_contract(self):
        for marker in (
            'data-story-prev',
            'data-story-next',
            'data-story-dots',
            'data-sticky-nav',
            'data-story-live aria-live="polite"',
            'aria-roledescription="carousel"',
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.body)

    def test_folk_speech_study_figures_preserve_the_documented_values(self):
        self.assertIn('class="story-slide__study-figures"', self.body)
        self.assertIn(">90<", self.body)
        self.assertIn(">97<", self.body)
        self.assertIn("Figures from the documented study cited in Sources and Further Reading.", self.body)
