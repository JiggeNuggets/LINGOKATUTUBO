import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from .models import PhrasebookEntry
from .services.resource_parity import analyze_resource_inventory, normalized_key, raw_key
from .services.translation_dataset import TranslationDataset, reset_translation_dataset


class ResourceInventoryParityTests(SimpleTestCase):
    def test_keys_distinguish_raw_rows_and_normalized_rows(self):
        first = {"tagabawa": "Madayaw", "english": "Good!", "filipino": "Mabuti", "cebuano": "Maayo"}
        second = {"tagabawa": "madayaw", "english": " good ", "filipino": "mabuti", "cebuano": "maayo"}
        self.assertNotEqual(raw_key(first), raw_key(second))
        self.assertEqual(normalized_key(first), normalized_key(second))

    @patch("translator.services.resource_parity.load_database_rows")
    @patch("translator.services.resource_parity.load_legacy_rows")
    def test_inventory_explains_normalized_duplicates_and_conservative_recommendations(self, legacy_loader, database_loader):
        legacy_loader.return_value = [
            {"origin": "json", "row_number": 1, "tagabawa": "Madayaw", "english": "Good!", "filipino": "Mabuti", "cebuano": "Maayo", "source": "json"},
            {"origin": "csv", "row_number": 2, "tagabawa": "madayaw", "english": " good ", "filipino": "mabuti", "cebuano": "maayo", "source": "csv"},
            {"origin": "csv", "row_number": 3, "tagabawa": "Bag-o", "english": "New", "filipino": "Bago", "cebuano": "Bag-o", "source": "csv"},
        ]
        database_loader.return_value = [
            {"origin": "database", "row_number": 1, "tagabawa": "Madayaw", "english": "Good", "filipino": "Mabuti", "cebuano": "Maayo", "source": "database"},
        ]
        report = analyze_resource_inventory()
        self.assertEqual(report["legacy"]["rows"], 3)
        self.assertEqual(report["legacy"]["unique_normalized_keys"], 2)
        self.assertEqual(report["legacy"]["duplicate_normalized_rows"], 1)
        self.assertEqual(report["legacy_only_unique_normalized_keys"], 1)
        self.assertEqual(report["classification_summary"], {"corpus_only_phrase": 1})
        self.assertEqual(report["recommendation_summary"], {"KEEP_LEGACY_ONLY": 1})


class ControlledRuntimeParityTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.dataset_path = Path(self.tempdir.name) / "legacy.json"
        self.dataset_path.write_text(json.dumps({"rows": [
            {"english": "Known phrase", "tagabawa": "Nailhan nga pulong", "filipino": "Kilalang parirala", "cebuano": "Iladong hugpong"},
        ]}), encoding="utf-8")
        PhrasebookEntry.objects.create(
            english="Known phrase", tagabawa="Nailhan nga pulong",
            filipino="Kilalang parirala", cebuano="Iladong hugpong", source="test",
        )
        self.legacy = TranslationDataset(
            str(self.dataset_path), include_default_corpus=False,
            include_validated_imports=False, data_mode="development_unverified",
        )
        self.database = TranslationDataset(data_mode="development_resources")

    def tearDown(self):
        reset_translation_dataset()

    def test_quick_translation_uses_the_same_result_for_controlled_shared_entry(self):
        from .services import translation_dataset as dataset_module
        from .services import quick_translate_text

        dataset_module._dataset = self.legacy
        legacy = quick_translate_text("Known phrase", "english", "tagabawa")
        dataset_module._dataset = self.database
        database = quick_translate_text("Known phrase", "english", "tagabawa")
        self.assertEqual(legacy["translated"], database["translated"])
        self.assertEqual(legacy["method"], database["method"])

    def test_document_layout_retains_known_and_unknown_text_in_both_modes(self):
        from .services.pipeline_service import PipelineService

        layout = [{"blocks": [{"type": "text", "lines": [
            {"text": "Known phrase"}, {"text": "Unknown sentence"},
        ]}]}]
        outcomes = []
        for dataset in (self.legacy, self.database):
            service = PipelineService()
            service.translation_dataset = dataset
            translated = service._translate_layout(layout, "english", "tagabawa", [])
            outcomes.append([
                (translated["0_0_0"]["translated"], translated["0_0_0"]["method"], translated["0_0_0"]["needs_review"]),
                (translated["0_0_1"]["translated"], translated["0_0_1"]["method"], translated["0_0_1"]["needs_review"]),
            ])
        self.assertEqual(outcomes[0], outcomes[1])
        self.assertEqual(outcomes[0][0][0], "Nailhan nga pulong")
        self.assertEqual(outcomes[0][1], ("Unknown sentence", "unknown_for_review", True))
