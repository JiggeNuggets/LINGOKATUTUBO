from django.test import TestCase
from django.urls import reverse

from translator.editorial_content import get_public_content


class PublicEditorialReadingTests(TestCase):
    """Every documented chapter remains visible and directly addressable."""

    def test_chapter_links_reach_visible_sections_on_each_public_page(self):
        for page_key in ("bagobo_tagabawa", "community", "nature", "culture"):
            with self.subTest(page=page_key):
                body = self.client.get(reverse(f"translator:{page_key}")).content.decode("utf-8")
                for section in get_public_content(page_key)["sections"]:
                    slug = section["slug"]
                    self.assertIn(f'href="#{slug}"', body)
                    self.assertIn(f'id="{slug}"', body)
                    self.assertIn(section["title"], body)
                self.assertNotIn('data-story-rail', body)
                self.assertNotIn('aria-roledescription="carousel"', body)

    def test_sources_and_other_stories_remain_reachable(self):
        for page_key in ("bagobo_tagabawa", "community", "nature", "culture"):
            with self.subTest(page=page_key):
                body = self.client.get(reverse(f"translator:{page_key}")).content.decode("utf-8")
                self.assertIn('href="#sources"', body)
                self.assertIn('id="sources"', body)
                self.assertIn('aria-label="Other stories"', body)
