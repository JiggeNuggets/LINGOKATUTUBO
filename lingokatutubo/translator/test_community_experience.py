from django.test import TestCase
from django.urls import reverse


class CommunityExperienceTests(TestCase):
    def setUp(self):
        self.response = self.client.get(reverse("translator:community"))
        self.body = self.response.content.decode("utf-8")

    def test_community_presents_three_documented_chapters(self):
        self.assertEqual(self.response.status_code, 200)
        self.assertEqual(self.body.count('class="chapter chapter'), 2)
        for slug, title in (
            ("community-education", "Community-Based Education in Astorga"),
            ("learning-materials", "Learning Materials With Local Context"),
            ("folk-speech", "Folk Speech in Scholarly Documentation"),
        ):
            self.assertIn(f'href="#{slug}"', self.body)
            self.assertIn(f'id="{slug}"', self.body)
            self.assertIn(title, self.body)

    def test_usep_photographs_are_labeled_as_campus_context(self):
        self.assertIn("usep-obrero-gate-960.jpg", self.body)
        self.assertIn("usep-obrero-entrance-960.jpg", self.body)
        self.assertIn("Campus context; this does not depict the PANGANDOY program.", self.body)
        self.assertIn("Campus context; this does not depict a PANGANDOY writeshop.", self.body)
        self.assertIn("https://creativecommons.org/licenses/by-sa/4.0/", self.body)
        self.assertNotIn('id="photographs"', self.body)

    def test_community_publishes_sources_and_related_destinations(self):
        self.assertIn("Sources and further reading", self.body)
        self.assertIn("Pangandoy Extension Program", self.body)
        self.assertIn("A study of Bagobo Tagabawa folk speech", self.body)
        for route in ("bagobo_tagabawa", "culture", "nature", "translate"):
            self.assertIn(f'href="{reverse(f"translator:{route}")}"', self.body)

    def test_folk_speech_study_figures_keep_documented_values(self):
        self.assertIn('aria-label="Documented study figures"', self.body)
        self.assertIn(">90</strong>", self.body)
        self.assertIn(">97</strong>", self.body)
        self.assertIn("Proverbs", self.body)
        self.assertIn("Riddles", self.body)
