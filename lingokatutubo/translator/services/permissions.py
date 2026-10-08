"""Server-side role policy for translation and governance information."""


def _is_authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def is_teacher(user):
    return _is_authenticated(user) and user.groups.filter(name="Teacher").exists()


def is_validator(user):
    return _is_authenticated(user) and user.has_perm("translator.review_language_entry")


def is_administrator(user):
    return _is_authenticated(user) and (user.is_staff or user.groups.filter(name="Administrator").exists())


def can_view_translation_details(user):
    """Detailed job and segment metadata is for validators and superusers."""
    return _is_authenticated(user) and (user.is_superuser or is_validator(user))


def can_view_validation_markers(user):
    return can_view_translation_details(user)


def can_download_teacher_copy(user):
    return _is_authenticated(user) and (user.is_superuser or is_teacher(user) or is_validator(user))


def can_download_validator_copy(user):
    return can_view_validation_markers(user)


def can_view_governance_information(user):
    return _is_authenticated(user) and (user.is_superuser or is_administrator(user))


def can_manage_translation_resources(user):
    """Routine resource maintenance is separate from validator governance."""
    return _is_authenticated(user) and (
        user.is_superuser or user.has_perm("translator.manage_language_resources")
    )


def can_view_system_diagnostics(user):
    return _is_authenticated(user) and user.is_superuser


def translation_permissions(user):
    """A template-safe capability map; views must still enforce each action."""
    return {
        "is_teacher": is_teacher(user),
        "is_validator": is_validator(user),
        "is_administrator": is_administrator(user),
        "is_superuser": bool(_is_authenticated(user) and user.is_superuser),
        "can_view_translation_details": can_view_translation_details(user),
        "can_view_validation_markers": can_view_validation_markers(user),
        "can_download_teacher_copy": can_download_teacher_copy(user),
        "can_download_validator_copy": can_download_validator_copy(user),
        "can_view_governance_information": can_view_governance_information(user),
        "can_manage_translation_resources": can_manage_translation_resources(user),
        "can_view_system_diagnostics": can_view_system_diagnostics(user),
    }
