import zipfile
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from PIL import Image, UnidentifiedImageError

from .models import PhrasebookEntry
from .services.resource_management import LANGUAGE_FIELDS, usable_language_count


LANGUAGE_CHOICES = [
    ("auto", "Auto-Detect"),
    ("english", "English"),
    ("filipino", "Filipino / Tagalog"),
    ("cebuano", "Cebuano"),
    ("tagabawa", "Bagobo-Tagabawa"),
]

TARGET_LANGUAGE_CHOICES = [
    ("tagabawa", "Bagobo-Tagabawa"),
    ("english", "English"),
    ("filipino", "Filipino / Tagalog"),
    ("cebuano", "Cebuano"),
]

DEFAULT_OCR_LANGUAGES = "eng+fil+ceb"

ALLOWED_EXTENSIONS = {".pdf", ".docx"}
ALLOWED_CONTENT_TYPES = {
    ".pdf": {"application/pdf", "application/x-pdf"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
}


class DocumentUploadForm(forms.Form):
    file = forms.FileField()
    source_language = forms.ChoiceField(choices=LANGUAGE_CHOICES, initial="auto")
    target_language = forms.ChoiceField(choices=TARGET_LANGUAGE_CHOICES, initial="tagabawa")
    ocr_languages = forms.CharField(
        required=False,
        max_length=128,
        widget=forms.HiddenInput(),
        initial=DEFAULT_OCR_LANGUAGES,
    )

    def clean(self):
        cleaned_data = super().clean()
        raw_ocr = (cleaned_data.get("ocr_languages") or "").strip()
        cleaned_data["ocr_languages"] = raw_ocr or DEFAULT_OCR_LANGUAGES

        return cleaned_data

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        extension = Path(uploaded.name.lower()).suffix
        if extension not in ALLOWED_EXTENSIONS:
            raise forms.ValidationError("Please upload a PDF or DOCX document.")
        if uploaded.size > settings.LINGOKATUTUBO_MAX_UPLOAD_BYTES:
            max_mb = settings.LINGOKATUTUBO_MAX_UPLOAD_BYTES // (1024 * 1024)
            raise forms.ValidationError(f"File is too large. Maximum size is {max_mb} MB.")
        content_type = (getattr(uploaded, "content_type", "") or "").lower()
        allowed_types = ALLOWED_CONTENT_TYPES.get(extension, set())
        if content_type and content_type not in allowed_types:
            raise forms.ValidationError("The uploaded file type does not match its extension.")
        self._validate_file_signature(uploaded, extension)
        return uploaded

    def _validate_file_signature(self, uploaded, extension: str) -> None:
        try:
            uploaded.seek(0)
            header = uploaded.read(8192)
            uploaded.seek(0)
        except Exception as exc:
            raise forms.ValidationError("Could not inspect the uploaded file.") from exc

        if extension == ".pdf":
            if not header.startswith(b"%PDF-"):
                raise forms.ValidationError("The uploaded PDF is not a valid PDF file.")
            return

        if extension == ".docx":
            if not header.startswith(b"PK"):
                raise forms.ValidationError("The uploaded DOCX is not a valid Office document.")
            try:
                with zipfile.ZipFile(uploaded) as archive:
                    names = set(archive.namelist())
                    if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                        raise forms.ValidationError("The uploaded DOCX is missing required document parts.")
            except zipfile.BadZipFile as exc:
                raise forms.ValidationError("The uploaded DOCX is not a valid ZIP package.") from exc
            finally:
                uploaded.seek(0)
            return

        raise forms.ValidationError("Please upload a PDF or DOCX document.")


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2"]


class TranslationResourceForm(forms.ModelForm):
    """The routine, non-governance fields exposed to resource managers."""

    class Meta:
        model = PhrasebookEntry
        fields = [
            "tagabawa", "english", "filipino", "cebuano", "part_of_speech",
            "topic", "source", "notes", "is_active",
        ]
        labels = {
            "tagabawa": "Bagobo-Tagabawa",
            "part_of_speech": "Entry type",
            "topic": "Category",
            "is_active": "Active",
        }
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].required = False
        self.fields["notes"].required = False
        self.fields["part_of_speech"].required = False
        self.fields["topic"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("is_active") and usable_language_count(cleaned) < 2:
            raise forms.ValidationError(
                "Active resources require at least two usable language values."
            )
        cleaned["source"] = (cleaned.get("source") or "translation_resources").strip()
        return cleaned


class TranslationResourceImportForm(forms.Form):
    file = forms.FileField(label="CSV or JSON resource file")

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        suffix = Path(uploaded.name.lower()).suffix
        if suffix not in {".csv", ".json"}:
            raise forms.ValidationError("Upload a CSV or JSON resource file.")
        if uploaded.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Resource imports are limited to 5 MB.")
        return uploaded


class ResourceMatchTesterForm(forms.Form):
    source_language = forms.ChoiceField(choices=TARGET_LANGUAGE_CHOICES)
    target_language = forms.ChoiceField(choices=TARGET_LANGUAGE_CHOICES)
    text = forms.CharField(label="Text to test", max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("source_language") == cleaned.get("target_language"):
            raise forms.ValidationError("Choose different source and target languages.")
        return cleaned
