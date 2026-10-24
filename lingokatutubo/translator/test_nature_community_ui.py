from pathlib import Path

from django.test import TestCase
from django.urls import reverse


class NatureAndCommunityPresentationTests(TestCase):
    def test_public_pages_use_scoped_editorial_styles(self):
        for route in ("bagobo_tagabawa", "community", "nature", "culture"):
            with self.subTest(route=route):
                body = self.client.get(reverse(f"translator:{route}")).content.decode("utf-8")
                self.assertIn(f'data-editorial-page="{route}"', body)
                self.assertIn('/static/css/editorial-pages.css', body)

    def test_nature_excludes_unreviewed_media_and_labels_video_review(self):
        body = self.client.get(reverse("translator:nature")).content.decode("utf-8")
        for name in ("mount-apo-ecology", "mount-apo-agroforestry", "mount-apo-stewardship"):
            self.assertNotIn(f'/static/images/editorial/{name}', body)
        self.assertIn('id="documentary-review"', body)
        self.assertIn("review pending", body)
        self.assertIn('data-count="2"', body)

    def test_gallery_rules_fill_two_and_four_image_records(self):
        css = (Path(__file__).resolve().parents[1] / "static" / "css" / "editorial-pages.css").read_text(
            encoding="utf-8"
        )
        self.assertIn('.photographs__list[data-count="4"]', css)
        self.assertIn('.photographs__list[data-count="2"]', css)
        self.assertIn('@media(prefers-reduced-motion:reduce)', css)
        bagobo = self.client.get(reverse("translator:bagobo_tagabawa")).content.decode("utf-8")
        self.assertIn('data-count="4"', bagobo)
