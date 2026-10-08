from django.contrib.auth.models import Group, Permission
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class Phase4NavigationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("learner", password="safe-password")

    def test_dashboard_requires_authentication_and_is_owner_safe(self):
        self.assertEqual(self.client.get(reverse("translator:dashboard")).status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(reverse("translator:dashboard"))
        self.assertContains(response, "Recent documents")
        self.assertNotContains(response, "Validator work")

    def test_validator_navigation_is_permission_scoped(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("translator:home"))
        self.assertNotContains(response, "Language Review Queue")
        self.user.user_permissions.add(Permission.objects.get(codename="review_language_entry"))
        response = self.client.get(reverse("translator:home"))
        self.assertContains(response, "Language Review Queue")
