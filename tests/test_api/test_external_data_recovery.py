import time

import pytest

from src.services.external_data_recovery import (
    ExternalFinancialDataRecoveryAgent,
    ExternalSourceRegistry,
    MissingEvidenceItem,
    RecoveryRequest,
)


class FakeSearch:
    def __init__(self, results):
        self.results = results
        self.calls = 0

    def search(self, query, max_results):
        self.calls += 1
        return self.results


class FlakySearch:
    def __init__(self):
        self.calls = 0

    def search(self, query, max_results):
        self.calls += 1
        if self.calls < 2:
            raise TimeoutError("temporary")
        return [{
            "url": "https://hpg.com.vn/investor/annual-report-2024.pdf",
            "title": "HPG Annual Report 2024",
            "publisher": "Hoa Phat Group",
            "value": "0.24",
        }]


class SlowSearch:
    def search(self, query, max_results):
        time.sleep(0.3)
        return []


def test_tier_one_source_is_selected_and_metadata_is_preserved():
    client = FakeSearch([
        {"url": "https://news.example.com/hpg", "title": "HPG ROE", "publisher": "News", "value": "0.10"},
        {"url": "https://hpg.com.vn/annual-report.pdf", "title": "Audited Annual Report", "publisher": "HPG", "value": "0.24"},
    ])
    result = ExternalFinancialDataRecoveryAgent(client).recover({
        "company": "HPG", "missing": [{"metric": "ROE", "year": 2024}],
    })
    assert len(result.evidence) == 1
    item = result.evidence[0]
    assert item.source_type == "TIER_1"
    assert item.confidence == "HIGH"
    assert item.value == "0.24"
    assert item.metadata["numerical_truth"] is False
    assert item.metadata["year"] == 2024


def test_unknown_or_incomplete_sources_are_rejected():
    client = FakeSearch([{"title": "No URL", "publisher": "x", "value": "1"}])
    result = ExternalFinancialDataRecoveryAgent(client).recover({
        "company": "HPG", "missing": [{"metric": "ROE", "year": 2024}],
    })
    assert result.evidence == []


def test_retry_recovers_after_transient_failure():
    client = FlakySearch()
    result = ExternalFinancialDataRecoveryAgent(client, max_retries=2).recover({
        "company": "HPG", "missing": [{"metric": "ROE", "year": 2024}],
    })
    assert client.calls == 2
    assert result.evidence[0].metadata["attempts"] == 2


def test_timeout_returns_no_fabricated_evidence():
    result = ExternalFinancialDataRecoveryAgent(SlowSearch(), timeout_seconds=0.01, max_retries=0).recover({
        "company": "HPG", "missing": [{"metric": "ROE", "year": 2024}],
    })
    assert result.evidence == []


def test_request_and_source_registry_validation():
    request = RecoveryRequest(company="HPG", missing=[MissingEvidenceItem(metric="ROE", year=2024)])
    assert request.company == "HPG"
    assert ExternalSourceRegistry().rank({
        "url": "https://example.com/report.pdf", "title": "Annual Report", "publisher": "Example",
    }).tier == 1
    with pytest.raises(Exception):
        RecoveryRequest.model_validate({"company": "", "missing": []})

