import io
import re
import zipfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from translator.forms import DocumentUploadForm
from translator.editorial_media import APPROVED_EDITORIAL_IMAGE_PATHS, PUBLIC_EDITORIAL_MEDIA


class NavigationAndHomepageTests(TestCase):
    def _nav(self, response):
        body = response.content.decode("utf-8")
        start = body.index('<div class="nav-links"')
        end = body.index("</nav>", start)
        return body[start:end]

    def test_public_explore_pages_render_without_publishing_note_and_with_verified_content(self):
        for route_name, expected_text in (
            ("translator:bagobo_tagabawa", "Who Are the Bagobo-Tagabawa?"),
            ("translator:culture", "Traditional Inabal Weaving"),
            ("translator:nature", "Apo Sandawa: Mount Apo"),
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, "Content is being prepared")
                self.assertNotContains(response, "editorial-page__notice")
                self.assertContains(response, expected_text)
                self.assertContains(response, 'id="chapters"', html=False)
                self.assertContains(response, 'class="chapter-index shell"', html=False)
                self.assertContains(response, "Continue exploring")

    def test_salinta_monon_has_correct_dates_and_tagabawa_identity(self):
        response = self.client.get(reverse("translator:culture"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Salinta Monon")
        self.assertContains(response, "1920–2009")
        self.assertContains(response, "Tagabawa Bagobo textile weaver")
        self.assertNotContains(response, "1920–2003")
        self.assertNotContains(response, "1920-2003")

    def test_unverified_palusong_term_is_not_present_on_explore_pages(self):
        for route_name in ("translator:bagobo_tagabawa", "translator:culture", "translator:nature"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertNotContains(response, "palusong")

    def test_get_public_content_filters_unverified_and_review_needed_statuses(self):
        from translator.editorial_content import get_public_content
        content = get_public_content("culture")
        statuses = {s.get("status") for s in content["sections"]}
        self.assertTrue(statuses.issubset({"VERIFIED", "VERIFIED_BROADER_BAGOBO"}))
        self.assertNotIn("COMMUNITY_REVIEW_NEEDED", statuses)
        self.assertNotIn("NEEDS_RESEARCH", statuses)
        self.assertNotIn("REMOVE", statuses)

    def test_bagobo_tagabawa_renders_editorial_chapters(self):
        response = self.client.get(reverse("translator:bagobo_tagabawa"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bagobo-Tagabawa")
        self.assertNotContains(response, "Content is being prepared")
        self.assertContains(response, 'id="chapters"', html=False)
        self.assertContains(response, 'href="#who-are-they"', html=False)
        self.assertContains(response, 'id="who-are-they"', html=False)

    def test_public_editorial_pages_share_versioned_assets_and_continue_exploring(self):
        for route_name in ("translator:bagobo_tagabawa", "translator:culture", "translator:nature"):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                body = response.content.decode("utf-8")

                self.assertContains(response, "Continue exploring")
                self.assertIn("/static/css/styles.css?v=20260828-homepage-polish", body)
                self.assertIn("/static/js/app.js?v=20260826-appjs-init-recovery", body)
                self.assertIn("/static/css/editorial-pages.css", body)

    def test_bagobo_story_exposes_each_chapter_in_document_order(self):
        response = self.client.get(reverse("translator:bagobo_tagabawa"))
        body = response.content.decode("utf-8")
        chapter_ids = re.findall(r'<section class="chapter(?:\s[^"]*)?" id="([^"]+)"', body)
        self.assertEqual(chapter_ids, [
            "who-are-they", "homeland", "community", "land", "textiles", "living-culture"
        ])
        for chapter_id in chapter_ids:
            self.assertIn(f'href="#{chapter_id}"', body)
        self.assertNotIn('data-story-rail', body)

    def test_dom_content_loaded_initializers_are_defined(self):
        script = (Path(__file__).resolve().parents[1] / "static" / "js" / "app.js").read_text(
            encoding="utf-8"
        )
        ready_handler = re.search(
            r'document\.addEventListener\("DOMContentLoaded",\s*\(\)\s*=>\s*\{(?P<body>[\s\S]*?)\n\s*\}\);',
            script,
        )

        self.assertIsNotNone(ready_handler)
        calls = re.findall(r"^\s*(init[A-Za-z_$][\w$]*)\(\);", ready_handler.group("body"), re.MULTILINE)
        definitions = set(re.findall(r"^\s*function\s+(init[A-Za-z_$][\w$]*)\s*\(", script, re.MULTILINE))

        self.assertTrue(calls)
        self.assertEqual([], sorted(set(calls) - definitions))

    def test_home_leads_with_datu_and_keeps_unapproved_content_labeled(self):
        response = self.client.get(reverse("translator:home"))
        body = response.content.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn('<main class="landing-page">', body)
        self.assertIn('<h1 id="datu-heading">Datu Dalmacio Agton</h1>', body)
        self.assertIn("Archival image &middot; not Datu Agton", body)
        self.assertIn("Illustrative archival photograph &mdash; not Datu Dalmacio Agton.", body)
        self.assertIn('href="#his-story"', body)
        self.assertIn('class="landing-quote-disclosure"', body)
        self.assertIn("[Approved excerpt pending.]", body)
        self.assertIn("[Approved translation will appear here.", body)
        self.assertIn("Preview translation space", body)
        self.assertIn('href="/translate/">Try now', body)

    def test_footer_exposes_explore_and_translation_destinations_without_about(self):
        response = self.client.get(reverse("translator:home"))
        body = response.content.decode("utf-8")
        footer = body[body.index('<footer class="site-footer"'):]

        self.assertIn('class="footer-nav"', footer)
        self.assertIn(reverse("translator:bagobo_tagabawa"), footer)
        self.assertIn(reverse("translator:translate"), footer)
        self.assertNotIn("/about/", footer)

    def test_logo_is_the_accessible_home_link_and_explore_is_active_on_editorial_pages(self):
        response = self.client.get(reverse("translator:culture"))
        body = response.content.decode("utf-8")
        self.assertIn('aria-label="LingoKatutubo home"', body)
        self.assertIn(reverse("translator:home"), body)
        self.assertIn('class="nav-dropdown__trigger is-active"', body)
        self.assertIn('href="/culture/" aria-current="page"', body)

    def test_header_and_footer_use_canonical_branding_and_favicons(self):
        for route_name in (
            "translator:home",
            "translator:bagobo_tagabawa",
            "translator:culture",
            "translator:nature",
            "translator:community",
            "translator:login",
            "translator:signup",
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                body = response.content.decode("utf-8")
                self.assertIn("/static/images/branding/lingokatutubo-logo.png", body)
                self.assertIn('class="brand-mark"', body)
                self.assertIn("/static/images/branding/favicon-32x32.png", body)
                self.assertIn("/static/images/branding/favicon-48x48.png", body)
                self.assertIn("/static/images/branding/apple-touch-icon.png", body)

        for asset in (
            "images/branding/lingokatutubo-logo.png",
            "images/branding/favicon-32x32.png",
            "images/branding/favicon-48x48.png",
            "images/branding/apple-touch-icon.png",
        ):
            with self.subTest(asset=asset):
                self.assertIsNotNone(finders.find(asset), f"Static asset {asset} must exist")

    def test_authenticated_navigation_keeps_workflow_and_secure_user_menu(self):
        user = get_user_model().objects.create_user(username="navuser", password="safe-password-123")
        self.client.force_login(user)
        nav = self._nav(self.client.get(reverse("translator:home")))
        self.assertIn(">Translate<", nav)
        self.assertIn(">Dashboard<", nav)
        self.assertIn(">History<", nav)
        self.assertIn("nav-dropdown--user", nav)
        self.assertIn('method="post" action="/accounts/logout/"', nav)
        self.assertNotIn("Translation Resources", nav)
        self.assertNotIn(">Home<", nav)

    def test_privileged_navigation_remains_permission_gated(self):
        administrator = get_user_model().objects.create_superuser(
            username="navadmin", email="navadmin@example.test", password="safe-password-123"
        )
        self.client.force_login(administrator)
        nav = self._nav(self.client.get(reverse("translator:home")))
        self.assertIn("nav-dropdown--admin", nav)
        self.assertIn("Translation Resources", nav)
        self.assertIn("Match Tester", nav)
        self.assertIn("Django Admin", nav)

    def test_dropdown_script_supports_outside_click_and_escape(self):
        from django.conf import settings
        script_path = settings.BASE_DIR / "static" / "js" / "app.js"
        if not script_path.exists():
            script_path = Path("static/js/app.js")
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        self.assertIn("function initNavigationDropdowns", script)
        self.assertIn('event.key !== "Escape"', script)
        self.assertIn('document.addEventListener("click"', script)
        self.assertIn('dropdown.classList.toggle("is-open", isOpen)', script)
        response = self.client.get(reverse("translator:home"))
        nav = self._nav(response)
        self.assertIn('data-nav-dropdown-trigger', nav)
        self.assertIn('id="explore-menu"', nav)
        self.assertIn('aria-expanded="false"', nav)
        self.assertIn('id="explore-menu" aria-label="Explore LingoKatutubo" hidden', nav)
        self.assertNotIn('<details class="nav-dropdown"', nav)
        self.assertNotIn("<summary", nav)
        self.assertEqual(nav.count("nav-dropdown__chevron"), 1)


class PublicEditorialHeroSystemTests(TestCase):
    """Guard the approved shared editorial opening and responsive layout."""

    public_pages = (
        ("translator:bagobo_tagabawa", "Bagobo-Tagabawa"),
        ("translator:culture", "Culture"),
        ("translator:nature", "Nature"),
        ("translator:community", "Community"),
    )

    def test_all_public_pages_render_the_shared_editorial_hero_anatomy(self):
        for route_name, expected_title in self.public_pages:
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                body = response.content.decode("utf-8")

                self.assertEqual(response.status_code, 200)
                self.assertIn('class="masthead"', body)
                self.assertIn('class="masthead__image"', body)
                self.assertIn('class="masthead__intro"', body)
                self.assertIn('class="story-figure story-figure--hero"', body)
                self.assertIn('class="page-picker shell"', body)
                self.assertIn(expected_title, body)

    def test_shared_hero_css_includes_responsive_media_and_short_height_rules(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "editorial-pages.css").read_text(
            encoding="utf-8"
        )
        self.assertIn(".masthead__image", stylesheet)
        self.assertIn(".masthead__body", stylesheet)
        self.assertIn(".story-figure--hero", stylesheet)
        self.assertIn("woven-pattern-placeholder.svg", stylesheet)

    def test_shared_hero_stacks_at_the_public_tablet_breakpoint(self):
        stylesheet = (Path(__file__).resolve().parents[1] / "static" / "css" / "editorial-pages.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("@media(max-width:800px)", stylesheet)
        self.assertIn(".masthead__body,.chapter-index,.chapter__grid{grid-template-columns:1fr}", stylesheet)


class VerifiedEditorialMediaTests(TestCase):
    """Keep public-media records, local files, and visible credit in sync."""

    page_media = (
        ("translator:bagobo_tagabawa", "bagobo_tagabawa"),
        ("translator:culture", "culture"),
        ("translator:nature", "nature"),
        ("translator:community", "community"),
    )

    def test_approved_editorial_variants_are_collectable_static_files(self):
        for page_key, media_context in PUBLIC_EDITORIAL_MEDIA.items():
            records = [media_context["hero_media"]]
            records.extend(media_context.get("explore_cards", {}).values())
            records.extend(media_context.get("gallery_items", ()))
            for record in records:
                for size in ("image_640", "image_960", "image_1440"):
                    with self.subTest(page=page_key, image=record[size]):
                        self.assertIsNotNone(finders.find(record[size]))

    def test_each_public_hero_uses_approved_local_media_with_credit(self):
        for route_name, media_key in self.page_media:
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                body = response.content.decode("utf-8")
                media = PUBLIC_EDITORIAL_MEDIA[media_key]["hero_media"]

                self.assertEqual(response.status_code, 200)
                self.assertIn(media["image_960"], body)
                self.assertIn(media["photographer"], body)
                self.assertIn(media["source_title"], body)
                self.assertIn(media["license"], body)
                self.assertIn(media["source_url"], body)
                self.assertIn('fetchpriority="high"', body)
                self.assertIn("srcset=", body)
                self.assertIn("sizes=", body)

    def test_home_explore_cards_use_four_distinct_approved_media_records(self):
        response = self.client.get(reverse("translator:home"))
        body = response.content.decode("utf-8")
        cards = PUBLIC_EDITORIAL_MEDIA["home"]["explore_cards"]

        self.assertEqual(len({cards[key]["image_640"] for key in cards}), 4)
        for record in cards.values():
            self.assertIn(record["image_640"], body)
            self.assertIn(record["author"], body)
        self.assertIn('loading="lazy"', body)

    def test_culture_gallery_contains_complete_approved_source_records(self):
        response = self.client.get(reverse("translator:culture"))
        body = response.content.decode("utf-8")

        self.assertContains(response, 'id="photographs"', html=False)
        self.assertContains(response, 'data-count="2"', html=False)
        for record in PUBLIC_EDITORIAL_MEDIA["culture"]["gallery_items"]:
            self.assertIn(record["photographer"], body)
            self.assertIn(record["source_title"], body)
            self.assertIn(record["source_url"], body)
            self.assertIn(record["license_url"], body)

    def test_bagobo_gallery_is_rendered_and_linked_from_story_navigation(self):
        response = self.client.get(reverse("translator:bagobo_tagabawa"))
        body = response.content.decode("utf-8")

        self.assertContains(response, 'id="photographs"', html=False)
        self.assertContains(response, 'data-count="4"', html=False)
        self.assertIn('href="#photographs"', body)
        for record in PUBLIC_EDITORIAL_MEDIA["bagobo_tagabawa"]["gallery_items"]:
            self.assertIn(record["image_960"], body)
            self.assertIn(record["source_url"], body)

    def test_nature_gallery_contains_complete_approved_source_records(self):
        response = self.client.get(reverse("translator:nature"))
        body = response.content.decode("utf-8")

        self.assertContains(response, 'id="photographs"', html=False)
        self.assertContains(response, 'data-count="2"', html=False)
        for record in PUBLIC_EDITORIAL_MEDIA["nature"]["gallery_items"]:
            if record["image_960"] not in APPROVED_EDITORIAL_IMAGE_PATHS:
                self.assertNotIn(record["image_960"], body)
                continue
            self.assertIn(record["photographer"], body)
            self.assertIn(record["source_title"], body)
            self.assertIn(record["source_url"], body)

    def test_continue_exploring_links_are_reciprocal_and_reachable(self):
        page_checks = {
            "translator:bagobo_tagabawa": ("/culture/", "/nature/"),
            "translator:culture": ("/bagobo-tagabawa/", "/nature/"),
            "translator:nature": ("/bagobo-tagabawa/", "/culture/"),
        }
        for route_name, expected_paths in page_checks.items():
            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                body = response.content.decode("utf-8")
                for path in expected_paths:
                    self.assertIn(f'href="{path}"', body)
                self.assertIn('href="/translate/"', body)

    def test_home_renders_four_credited_discovery_paths(self):
        response = self.client.get(reverse("translator:home"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")

        self.assertIn('class="landing-discovery-grid"', body)
        for route_name in ("bagobo_tagabawa", "culture", "nature", "community"):
            self.assertIn(f'href="{reverse("translator:" + route_name)}"', body)
        self.assertEqual(body.count('class="landing-discovery-card__credit"'), 4)
        self.assertIn("Not Datu Agton.", body)

    def test_community_route_renders_verified_interactive_experience(self):
        response = self.client.get(reverse("translator:community"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Community Life, Learning &amp; Continuity")
        self.assertContains(response, 'id="chapters"', html=False)
        self.assertContains(response, "Community-Based Education in Astorga")
        self.assertContains(response, "Campus context; this does not depict the PANGANDOY program.")
        self.assertContains(response, "Campus context; this does not depict a PANGANDOY writeshop.")
        self.assertContains(response, "usep-obrero-gate-960.jpg")
        self.assertContains(response, "usep-obrero-entrance-960.jpg")


class DocumentUploadFormatRestrictionTests(TestCase):
    """Verify supported format restrictions to PDF and DOCX only across UI and backend."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="formatuser", password="safe-password-123"
        )

    def _valid_docx_bytes(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'></Types>")
            z.writestr("word/document.xml", "<w:document xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'></w:document>")
        return buf.getvalue()

    def test_translate_page_restricts_accept_attribute_and_helper_text(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("translator:translate"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'accept=".pdf,.docx"')
        self.assertContains(response, "PDF or DOCX · up to 50 MB")
        self.assertContains(response, 'data-max-file-bytes="52428800"')
        # Ensure file input does not accept non-document types
        self.assertNotContains(response, 'accept=".pdf,.docx,.jpg')
        self.assertNotContains(response, "Supported: PDF, DOCX, JPG")

    def test_pdf_upload_is_accepted_by_form(self):
        pdf_file = SimpleUploadedFile(
            "sample.pdf",
            b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF",
            content_type="application/pdf",
        )
        form = DocumentUploadForm(
            data={"source_language": "english", "target_language": "tagabawa"},
            files={"file": pdf_file},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_docx_upload_is_accepted_by_form(self):
        docx_file = SimpleUploadedFile(
            "sample.docx",
            self._valid_docx_bytes(),
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        form = DocumentUploadForm(
            data={"source_language": "english", "target_language": "tagabawa"},
            files={"file": docx_file},
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_jpg_upload_is_rejected_with_clear_validation_message(self):
        jpg_file = SimpleUploadedFile(
            "sample.jpg",
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
            content_type="image/jpeg",
        )
        form = DocumentUploadForm(
            data={"source_language": "english", "target_language": "tagabawa"},
            files={"file": jpg_file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)
        self.assertIn("Please upload a PDF or DOCX document.", form.errors["file"])

    def test_png_upload_is_rejected_with_clear_validation_message(self):
        png_file = SimpleUploadedFile(
            "sample.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4",
            content_type="image/png",
        )
        form = DocumentUploadForm(
            data={"source_language": "english", "target_language": "tagabawa"},
            files={"file": png_file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)
        self.assertIn("Please upload a PDF or DOCX document.", form.errors["file"])

    def test_txt_upload_is_rejected_with_clear_validation_message(self):
        txt_file = SimpleUploadedFile(
            "sample.txt",
            b"Plain text content",
            content_type="text/plain",
        )
        form = DocumentUploadForm(
            data={"source_language": "english", "target_language": "tagabawa"},
            files={"file": txt_file},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)
        self.assertIn("Please upload a PDF or DOCX document.", form.errors["file"])
