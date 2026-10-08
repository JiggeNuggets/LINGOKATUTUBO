import uuid

from django.conf import settings
from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Language(TimestampedModel):
    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=120)
    autonym = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class LanguagePair(TimestampedModel):
    source_language = models.ForeignKey(
        Language,
        related_name="source_pairs",
        on_delete=models.PROTECT,
    )
    target_language = models.ForeignKey(
        Language,
        related_name="target_pairs",
        on_delete=models.PROTECT,
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["source_language__name", "target_language__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source_language", "target_language"],
                name="translator_unique_language_pair",
            ),
            models.CheckConstraint(
                check=~models.Q(source_language=models.F("target_language")),
                name="translator_language_pair_not_identity",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_language.code} -> {self.target_language.code}"


class TranslationJob(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RETRYING = "retrying", "Retrying"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    class FileType(models.TextChoices):
        PDF = "pdf", "PDF"
        DOCX = "docx", "DOCX"
        JPG = "jpg", "JPG"
        PNG = "png", "PNG"
        TXT = "txt", "Text"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="translation_jobs",
        on_delete=models.CASCADE,
    )
    original_filename = models.CharField(max_length=255)
    upload_file_path = models.TextField(blank=True)
    file_type = models.CharField(max_length=16, choices=FileType.choices)
    detection_type = models.CharField(max_length=32, blank=True)
    source_language = models.CharField(max_length=32, default="auto")
    target_language = models.CharField(max_length=32, default="tagabawa")
    ocr_languages = models.CharField(max_length=128, blank=True)

    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.QUEUED,
        db_index=True,
    )
    progress = models.PositiveSmallIntegerField(default=0)
    current_phase = models.CharField(max_length=64, default="queued")
    current_step = models.CharField(max_length=160, default="Queued for processing")
    phase_message = models.TextField(blank=True)
    error = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    input_file_path = models.TextField(blank=True)
    output_file_path = models.TextField(blank=True)
    bilingual_file_path = models.TextField(blank=True)
    structure_file_path = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Soft-delete fields — deleted jobs are hidden from normal history queries
    # but preserved in the database for audit and recovery purposes.
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
            models.Index(fields=["owner", "is_deleted", "-created_at"], name="trans_owner_del_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.original_filename} ({self.status})"

    @property
    def job_id(self) -> str:
        return str(self.id)


class UploadedDocument(TimestampedModel):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="uploaded_documents",
        on_delete=models.CASCADE,
    )
    job = models.OneToOneField(
        TranslationJob,
        related_name="uploaded_document",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=16, choices=TranslationJob.FileType.choices)
    file_path = models.TextField()
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["owner", "-created_at"]),
            models.Index(fields=["file_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return self.original_filename


class DocumentPage(TimestampedModel):
    job = models.ForeignKey(
        TranslationJob,
        related_name="pages",
        on_delete=models.CASCADE,
    )
    page_number = models.PositiveIntegerField()
    width = models.FloatField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    rotation = models.IntegerField(default=0)
    source_image_path = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["job", "page_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "page_number"],
                name="translator_unique_page_per_job",
            )
        ]

    def __str__(self) -> str:
        return f"{self.job_id} page {self.page_number}"


class OCRResult(TimestampedModel):
    class Status(models.TextChoices):
        PENDING_REVIEW = "pending_review", "Pending review"
        ACCEPTED = "accepted", "Accepted"
        CORRECTED = "corrected", "Corrected"
        REJECTED = "rejected", "Rejected"

    job = models.ForeignKey(
        TranslationJob,
        related_name="ocr_results",
        on_delete=models.CASCADE,
    )
    page = models.ForeignKey(
        DocumentPage,
        related_name="ocr_results",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    engine = models.CharField(max_length=80, default="tesseract")
    language_codes = models.CharField(max_length=128, blank=True)
    text = models.TextField(blank=True)
    confidence = models.FloatField(null=True, blank=True)
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING_REVIEW,
        db_index=True,
    )
    warnings = models.JSONField(default=list, blank=True)
    raw_data = models.JSONField(default=dict, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="reviewed_ocr_results",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["job", "page__page_number", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "page", "engine"],
                name="translator_unique_ocr_result_per_page_engine",
            )
        ]
        indexes = [
            models.Index(fields=["job", "status"]),
            models.Index(fields=["engine", "status"]),
        ]

    def __str__(self) -> str:
        return f"OCR {self.engine} for {self.job_id}"


class TranslationSegment(TimestampedModel):
    job = models.ForeignKey(
        TranslationJob,
        related_name="segments",
        on_delete=models.CASCADE,
    )
    page = models.ForeignKey(
        DocumentPage,
        related_name="translation_segments",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    segment_index = models.PositiveIntegerField()
    source_text = models.TextField()
    translated_text = models.TextField(blank=True)
    source_language = models.CharField(max_length=32)
    target_language = models.CharField(max_length=32)
    method = models.CharField(max_length=64, blank=True)
    confidence = models.FloatField(null=True, blank=True)
    needs_review = models.BooleanField(default=False, db_index=True)
    bbox = models.JSONField(default=list, blank=True)
    glossary_matches = models.JSONField(default=list, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["job", "segment_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "segment_index"],
                name="translator_unique_segment_per_job",
            )
        ]
        indexes = [
            models.Index(fields=["job", "needs_review"]),
            models.Index(fields=["source_language", "target_language"]),
        ]

    def __str__(self) -> str:
        return f"{self.job_id} segment {self.segment_index}"


class UnknownTranslationRecord(TimestampedModel):
    """A private review queue item; the original document/upload is immutable."""
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        IN_REVIEW = "in_review", "In review"
        RESOLVED = "resolved", "Resolved"
        DISMISSED = "dismissed", "Dismissed"

    job = models.ForeignKey(TranslationJob, related_name="unknown_records", on_delete=models.CASCADE)
    page = models.ForeignKey(DocumentPage, related_name="unknown_records", on_delete=models.SET_NULL, null=True, blank=True)
    segment = models.OneToOneField(TranslationSegment, related_name="unknown_record", on_delete=models.CASCADE)
    source_text = models.TextField()
    normalized_text = models.TextField(blank=True)
    source_language = models.CharField(max_length=32)
    target_language = models.CharField(max_length=32)
    occurrence_count = models.PositiveIntegerField(default=1)
    ocr_confidence = models.FloatField(null=True, blank=True)
    reason = models.CharField(max_length=120, default="no_safe_match")
    suggested_related_entries = models.JSONField(default=list, blank=True)
    review_status = models.CharField(max_length=24, choices=ReviewStatus.choices, default=ReviewStatus.PENDING, db_index=True)
    submitted_correction_reference = models.CharField(max_length=255, blank=True)

    class Meta:
        indexes = [models.Index(fields=["review_status", "source_language", "target_language"])]

    def __str__(self):
        return f"Unknown segment {self.segment_id}"


class OCRCorrection(TimestampedModel):
    """Append-only OCR correction history.  OCRResult.text is never overwritten."""
    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    ocr_result = models.ForeignKey(OCRResult, related_name="corrections", on_delete=models.CASCADE)
    page = models.ForeignKey(DocumentPage, related_name="ocr_corrections", on_delete=models.CASCADE)
    original_ocr_text = models.TextField()
    corrected_text = models.TextField()
    bbox = models.JSONField(default=list, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="ocr_corrections", on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PROPOSED, db_index=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ocr_result", "created_at"]

    def __str__(self):
        return f"OCR correction {self.pk} ({self.status})"


class PhrasebookEntry(TimestampedModel):
    topic = models.CharField(max_length=120, blank=True, db_index=True)
    english = models.TextField(blank=True)
    tagabawa = models.TextField(blank=True)
    filipino = models.TextField(blank=True)
    cebuano = models.TextField(blank=True)
    source = models.CharField(max_length=120, default="phrasebook")
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_sme_verified = models.BooleanField(default=False, db_index=True)
    needs_review = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    part_of_speech = models.CharField(max_length=120, blank=True)
    word_sense = models.TextField(blank=True)
    source_title = models.CharField(max_length=255, blank=True)
    source_page = models.CharField(max_length=64, blank=True)
    source_owner = models.CharField(max_length=255, blank=True)
    license_status = models.CharField(max_length=64, default="unrecorded", db_index=True, blank=True)
    validation_status = models.CharField(max_length=32, default="pending", db_index=True, blank=True)
    validator = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="validated_phrasebook_entries",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    validation_date = models.DateField(null=True, blank=True)
    cultural_sensitivity_status = models.CharField(max_length=64, default="unreviewed", db_index=True, blank=True)
    access_restriction = models.CharField(max_length=64, default="internal", db_index=True, blank=True)
    revision_number = models.PositiveIntegerField(default=1)
    is_approved_for_runtime = models.BooleanField(default=False, db_index=True)
    required_reviews = models.PositiveSmallIntegerField(default=1)
    has_unresolved_conflict = models.BooleanField(default=False, db_index=True)
    import_batch = models.ForeignKey(
        "LanguageResourceImportBatch",
        related_name="entries",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["topic", "english", "id"]
        permissions = [
            ("review_language_entry", "Can review language-resource entries"),
            ("approve_runtime_entry", "Can approve verified entries for runtime"),
            ("manage_language_resources", "Can manage language-resource imports and reports"),
        ]
        indexes = [
            models.Index(fields=["is_active", "needs_review"]),
            models.Index(fields=["is_sme_verified", "needs_review"]),
        ]

    def governance_snapshot(self):
        return {
            "english": self.english, "tagabawa": self.tagabawa,
            "filipino": self.filipino, "cebuano": self.cebuano,
            "part_of_speech": self.part_of_speech, "word_sense": self.word_sense,
            "source_title": self.source_title, "source_page": self.source_page,
            "source_owner": self.source_owner, "license_status": self.license_status,
            "validation_status": self.validation_status,
            "cultural_sensitivity_status": self.cultural_sensitivity_status,
            "access_restriction": self.access_restriction, "notes": self.notes,
        }

    def save(self, *args, **kwargs):
        if self.pk:
            self.revision_number = (type(self).objects.filter(pk=self.pk).values_list("revision_number", flat=True).first() or 0) + 1
        super().save(*args, **kwargs)
        if not kwargs.get("raw", False):
            PhrasebookEntryRevision.objects.create(
                entry=self, revision_number=self.revision_number,
                snapshot=self.governance_snapshot(), validator=self.validator,
            )
    def __str__(self) -> str:
        return self.english or self.tagabawa or f"Phrasebook entry {self.pk}"


class PhrasebookEntryRevision(TimestampedModel):
    entry = models.ForeignKey(PhrasebookEntry, related_name="revisions", on_delete=models.CASCADE)
    revision_number = models.PositiveIntegerField()
    snapshot = models.JSONField(default=dict)
    validator = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="phrasebook_revisions", on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["entry", "-revision_number"]
        constraints = [models.UniqueConstraint(fields=["entry", "revision_number"], name="translator_unique_phrasebook_revision")]


class LanguageResourceImportBatch(TimestampedModel):
    """Immutable accounting record for one language-resource import attempt."""

    identifier = models.CharField(max_length=120, unique=True)
    source_filename = models.CharField(max_length=512)
    source_checksum_sha256 = models.CharField(max_length=64)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="language_resource_imports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    rows_processed = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    rows_duplicated = models.PositiveIntegerField(default=0)
    rows_conflicting = models.PositiveIntegerField(default=0)
    rows_incomplete = models.PositiveIntegerField(default=0)
    rows_requiring_review = models.PositiveIntegerField(default=0)
    is_dry_run = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    report_path = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]


class LanguageResourceIssue(TimestampedModel):
    class Category(models.TextChoices):
        EXACT_DUPLICATE = "exact_duplicate", "Exact duplicate"
        NORMALIZED_DUPLICATE = "normalized_duplicate", "Normalized duplicate"
        POSSIBLE_DUPLICATE = "possible_duplicate", "Possible duplicate"
        CONFLICTING_TRANSLATION = "conflicting_translation", "Conflicting translation"
        INCOMPLETE_RECORD = "incomplete_record", "Incomplete record"
        POSSIBLE_OCR_ARTIFACT = "possible_ocr_artifact", "Possible OCR artifact"
        MISSING_PROVENANCE = "missing_provenance", "Missing provenance"
        MISSING_LICENSE = "missing_license", "Missing license"
        VALIDATION_REQUIRED = "validation_required", "Validation required"

    batch = models.ForeignKey(LanguageResourceImportBatch, related_name="issues", on_delete=models.CASCADE)
    entry = models.ForeignKey(PhrasebookEntry, related_name="governance_issues", on_delete=models.SET_NULL, null=True, blank=True)
    category = models.CharField(max_length=48, choices=Category.choices, db_index=True)
    source_row_number = models.PositiveIntegerField(null=True, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    is_resolved = models.BooleanField(default=False, db_index=True)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="resolved_language_issues", on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_reason = models.TextField(blank=True)


class LanguageEntryReview(TimestampedModel):
    class Decision(models.TextChoices):
        KEEP_BOTH = "keep_both", "Keep both"
        DUPLICATE = "duplicate", "Duplicate"
        VERIFY = "verify", "Verify"
        REJECT = "reject", "Reject"
        RESTRICT = "restrict", "Restrict"
        REQUEST_REVIEW = "request_review", "Request another review"

    entry = models.ForeignKey(PhrasebookEntry, related_name="reviews", on_delete=models.PROTECT)
    reviewer = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="language_entry_reviews", on_delete=models.PROTECT)
    decision = models.CharField(max_length=32, choices=Decision.choices)
    notes = models.TextField()
    previous_state = models.JSONField(default=dict)
    new_state = models.JSONField(default=dict)
    related_entry_ids = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-created_at"]


class CorrectionSuggestion(TimestampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        UNDER_REVIEW = "under_review", "Under review"
        RESOLVED = "resolved", "Resolved"
        REJECTED = "rejected", "Rejected"

    job = models.ForeignKey(TranslationJob, related_name="correction_suggestions", on_delete=models.CASCADE)
    segment = models.ForeignKey(TranslationSegment, related_name="correction_suggestions", on_delete=models.SET_NULL, null=True, blank=True)
    source_text = models.TextField()
    displayed_translation = models.TextField(blank=True)
    suggested_correction = models.TextField()
    explanation = models.TextField(blank=True)
    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="correction_suggestions", on_delete=models.CASCADE)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.PENDING, db_index=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="reviewed_correction_suggestions", on_delete=models.SET_NULL, null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

class GlossaryTerm(TimestampedModel):
    language_pair = models.ForeignKey(
        LanguagePair,
        related_name="glossary_terms",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    source_term = models.CharField(max_length=255)
    target_term = models.CharField(max_length=255)
    domain = models.CharField(max_length=120, blank=True, db_index=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="created_glossary_terms",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["domain", "source_term"]
        constraints = [
            models.UniqueConstraint(
                fields=["language_pair", "source_term", "target_term"],
                name="translator_unique_glossary_term",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source_term} -> {self.target_term}"


class GeneratedOutput(TimestampedModel):
    class OutputType(models.TextChoices):
        TRANSLATED_PDF = "translated_pdf", "Translated PDF"
        BILINGUAL_ALIGNED = "bilingual_aligned", "Aligned bilingual document"
        BILINGUAL_ALTERNATING = "bilingual_alternating", "Alternating bilingual PDF"
        STRUCTURE_JSON = "structure_json", "Structure JSON"
        PREVIEW_IMAGE = "preview_image", "Preview image"

    job = models.ForeignKey(
        TranslationJob,
        related_name="generated_outputs",
        on_delete=models.CASCADE,
    )
    output_type = models.CharField(max_length=32, choices=OutputType.choices)
    file_format = models.CharField(max_length=16, default="pdf")
    file_path = models.TextField()
    file_size_bytes = models.PositiveBigIntegerField(default=0)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["job", "output_type", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "output_type", "file_path"],
                name="translator_unique_generated_output_path",
            )
        ]
        indexes = [
            models.Index(fields=["job", "output_type"]),
            models.Index(fields=["file_format", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.output_type} for {self.job_id}"


class DatasetImportBatch(TimestampedModel):
    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        PROCESSING = "processing", "Processing"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="dataset_imports",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    source_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.QUEUED)
    rows_total = models.PositiveIntegerField(default=0)
    rows_created = models.PositiveIntegerField(default=0)
    rows_updated = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    error_report = models.JSONField(default=list, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.source_filename} ({self.status})"


class SystemEventLog(models.Model):
    class Level(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        ERROR = "error", "Error"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="system_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    job = models.ForeignKey(
        TranslationJob,
        related_name="system_events",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    level = models.CharField(max_length=16, choices=Level.choices, default=Level.INFO)
    event_type = models.CharField(max_length=120, db_index=True)
    message = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["level", "-created_at"]),
            models.Index(fields=["event_type", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.level}: {self.event_type}"


class UserActivityLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="activity_logs",
        on_delete=models.CASCADE,
    )
    action = models.CharField(max_length=120, db_index=True)
    object_type = models.CharField(max_length=120, blank=True)
    object_id = models.CharField(max_length=120, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["action", "-created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} {self.action}"
