from src.services.evidence_fusion import EvidenceFusionNode


def test_source_priority_prefers_postgres_and_records_conflict():
    package = EvidenceFusionNode().fuse(
        postgres_evidence=[{"canonical_metric_code": "roe", "value": "0.24", "year": 2024}],
        derived_metrics=[{"metric": "roe", "value": 0.20, "year": 2024, "formula": "net_income / equity"}],
        external_evidence=[{"metric": "roe", "value": "0.18", "year": 2024, "source": "https://example.com/report"}],
    )
    assert package.facts[0].source == "POSTGRESQL"
    assert package.facts[0].value == "0.24"
    assert package.conflict is True
    assert package.conflicts[0].key == "roe:2024"
    assert package.limitations


def test_qdrant_is_interpretation_and_external_is_lower_priority():
    package = EvidenceFusionNode().fuse(
        qdrant_evidence=[{"text": "FPT tập trung vào công nghệ.", "source_id": "q-1"}],
        external_evidence=[{"metric": "revenue", "value": "100", "year": 2024, "source": "https://news.example/revenue"}],
    )
    assert package.interpretations[0].source == "QDRANT"
    assert package.facts[0].source == "EXTERNAL"
    assert package.conflict is False


def test_missing_values_are_not_fabricated():
    package = EvidenceFusionNode().fuse(
        postgres_evidence=[{"canonical_metric_code": "roe", "value": None, "year": 2024}],
        qdrant_evidence=[], derived_metrics=[], external_evidence=[],
    )
    assert package.facts == []
    assert package.limitations == ["No evidence was available for fusion."]

