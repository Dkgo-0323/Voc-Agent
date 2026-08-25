import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from pipelines.enrichment.aspect_extractor import AspectExtractor, PreparedDocument

FIXTURE = Path(__file__).parent / "fixtures" / "aspect_evidence_regression.json"


def test_human_labeled_aspect_evidence_regression_set() -> None:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(cases) >= 30
    assert {case["type"] for case in cases} == {"correct", "misclassification", "empty"}

    exact_mentions = 0
    accepted_mentions = 0
    expected_invalid = 0
    discarded_invalid = 0
    exact_label_matches = 0
    failed_documents = 0

    for case in cases:
        document_id = uuid5(NAMESPACE_URL, case["id"])
        documents, failures = AspectExtractor._validate_payload(
            {"documents": [{"document_id": str(document_id), "aspects": case["candidates"]}]},
            [PreparedDocument(document_id=document_id, body=case["body"])],
        )
        accepted = documents[0].aspects
        accepted_labels = [aspect.aspect_label for aspect in accepted]
        expected_labels = case["expected_labels"]
        exact_label_matches += accepted_labels == expected_labels
        accepted_mentions += len(accepted)
        exact_mentions += sum(aspect.mention_text in case["body"] for aspect in accepted)
        expected_invalid += max(0, len(case["candidates"]) - len(expected_labels))
        discarded_invalid += max(0, len(case["candidates"]) - len(accepted))
        failed_documents += document_id in failures

    excerpt_compliance = exact_mentions / accepted_mentions
    aspect_accuracy = exact_label_matches / len(cases)
    invalid_drop_rate = discarded_invalid / expected_invalid
    document_failure_rate = failed_documents / len(cases)
    expected_failed_documents = sum(
        bool(case["candidates"]) and not case["expected_labels"] for case in cases
    )

    assert excerpt_compliance == 1.0
    assert aspect_accuracy == 1.0
    assert invalid_drop_rate == 1.0
    assert failed_documents == expected_failed_documents
    assert document_failure_rate <= 0.40
