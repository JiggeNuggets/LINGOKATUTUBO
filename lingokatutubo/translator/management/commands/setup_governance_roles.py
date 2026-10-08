from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand


ROLE_PERMISSIONS = {
    "Learner": ["view_translationjob", "add_correctionsuggestion", "view_correctionsuggestion"],
    "Teacher": ["view_translationjob", "add_correctionsuggestion", "view_correctionsuggestion"],
    "Validator": ["view_phrasebookentry", "change_phrasebookentry", "view_phrasebookentryrevision", "add_languageentryreview", "view_languageentryreview", "review_language_entry"],
    "Administrator": ["view_phrasebookentry", "add_phrasebookentry", "change_phrasebookentry", "view_languageresourceimportbatch", "add_languageresourceimportbatch", "change_languageresourceimportbatch", "view_languageresourceissue", "manage_language_resources"],
}


class Command(BaseCommand):
    help = "Create Phase 2 governance groups with explicit permissions."

    def handle(self, *args, **options):
        for group_name, codenames in ROLE_PERMISSIONS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            permissions = Permission.objects.filter(content_type__app_label="translator", codename__in=codenames)
            group.permissions.set(permissions)
            self.stdout.write(f"{group_name}: {permissions.count()} permissions")
