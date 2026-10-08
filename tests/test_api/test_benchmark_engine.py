import pytest

from src.services.benchmark_engine import (
    BenchmarkAnalyzer,
    BenchmarkRegistry,
    BenchmarkResolver,
    BenchmarkType,
)


def _analyzer():
    registry = BenchmarkRegistry()
    registry.register_benchmark("roe", "FPT", 0.18, "HISTORICAL", "postgres", evidence_refs=["hist:roe:2023"], year=2023)
    registry.register_benchmark("roe", "FPT", 0.15, "INDUSTRY", "sector-report", evidence_refs=["industry:roe" ])
    return BenchmarkAnalyzer(BenchmarkResolver(registry))


def test_company_above_historical_and_industry_benchmarks():
    result = _analyzer().analyze({
        "company": "FPT", "metrics": [{"metric": "roe", "value": 0.22, "source": "POSTGRESQL", "evidence_refs": ["fact:roe:2024"], "year": 2024}],
        "signals": [],
    })
    assert {item.benchmark_type for item in result.benchmarks} == {BenchmarkType.HISTORICAL, BenchmarkType.INDUSTRY}
    assert all(item.position.value == "ABOVE" for item in result.benchmarks)
    assert all(item.evidence_refs for item in result.benchmarks)


def test_missing_benchmark_is_unknown():
    result = BenchmarkAnalyzer().analyze({
        "company": "FPT", "metrics": [{"metric": "roe", "value": 0.22, "source": "POSTGRESQL", "evidence_refs": ["fact:roe:2024"]}], "signals": [],
    })
    assert result.benchmarks[0].position.value == "UNKNOWN"
    assert "No registered benchmark" in result.limitations[0]


def test_conflicting_benchmarks_are_not_silently_resolved():
    registry = BenchmarkRegistry()
    registry.register_benchmark("roe", "FPT", 0.15, "INDUSTRY", "source-a", evidence_refs=["a"])
    registry.register_benchmark("roe", "FPT", 0.19, "INDUSTRY", "source-b", evidence_refs=["b"])
    result = BenchmarkAnalyzer(BenchmarkResolver(registry)).analyze({
        "company": "FPT", "metrics": [{"metric": "roe", "value": 0.22, "source": "POSTGRESQL", "evidence_refs": ["fact"]}], "signals": [],
    })
    assert result.benchmarks[0].position.value == "UNKNOWN"
    assert any("Conflicting" in limitation for limitation in result.limitations)


def test_registry_rejects_benchmark_without_source_and_empty_data_safe():
    with pytest.raises(ValueError):
        BenchmarkRegistry().register_benchmark("roe", "FPT", 0.2, "PEER")
    result = BenchmarkAnalyzer().analyze({"company": "FPT", "metrics": [], "signals": []})
    assert result.benchmarks == []
    assert result.limitations

