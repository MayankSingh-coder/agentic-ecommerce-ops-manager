from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.ecommerce_ops.agents.customer_insight_agent import CustomerInsightAgent
from app.ecommerce_ops.contracts import (
    AgentContext,
    AgentName,
    AgentRunStatus,
    CustomerInsightAgentInput,
    RiskLevel,
)
from app.llm.gateway_types import LLMGatewayResponse
from app.ecommerce_ops.repository import EcommerceOpsRepository
from app.ecommerce_ops.schemas import Product, ProductReturn, ReturnReason, Review
from tests.test_api.helpers import create_test_app


def create_customer_insight_input() -> CustomerInsightAgentInput:
    repository = EcommerceOpsRepository()
    return CustomerInsightAgentInput(
        context=AgentContext(
            run_id="customer-insight-test-run",
            prompt_version="customer_insight_agent_rules_v1",
            created_at=datetime.now(timezone.utc),
        ),
        products=repository.list_products(),
        reviews=repository.list_reviews(),
        returns=repository.list_returns(),
        lookback_days=30,
    )


def test_customer_insight_agent_generates_evidence_backed_clusters():
    report, run_record = CustomerInsightAgent().run(create_customer_insight_input())

    assert run_record.run_id == "customer-insight-test-run"
    assert run_record.agent_name == AgentName.customer_insight
    assert run_record.status == AgentRunStatus.succeeded
    assert len(report.clusters) == 2


def test_customer_insight_agent_clusters_size_mismatch_from_reviews_and_returns():
    report, _ = CustomerInsightAgent().run(create_customer_insight_input())

    cluster = next(item for item in report.clusters if item.sku == "SKU-1001")

    assert cluster.issue == "Size mismatch"
    assert cluster.review_count == 1
    assert cluster.return_count == 1
    assert cluster.severity == RiskLevel.high
    assert any("REV-7001" in evidence for evidence in cluster.representative_evidence)
    assert any("RET-3001" in evidence for evidence in cluster.representative_evidence)


def test_customer_insight_agent_clusters_battery_drain_as_high_priority_issue():
    report, _ = CustomerInsightAgent().run(create_customer_insight_input())

    cluster = next(item for item in report.clusters if item.sku == "SKU-1002")

    assert cluster.issue == "Battery drain"
    assert cluster.review_count == 1
    assert cluster.return_count == 1
    assert cluster.severity == RiskLevel.high
    assert "SKU-1002" in report.summary


def test_customer_insight_agent_api_returns_typed_report_response():
    client = TestClient(create_test_app())

    response = client.post(
        "/api/v1/ecommerce-ops/agents/customer-insights/run",
        json={"run_id": "customer-insight-api-test", "lookback_days": 30},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run"]["run_id"] == "customer-insight-api-test"
    assert payload["run"]["agent_name"] == "customer_insight"
    assert payload["run"]["status"] == "succeeded"
    assert len(payload["report"]["clusters"]) == 2
    assert payload["report"]["clusters"][0]["representative_evidence"]


def test_customer_insight_agent_accepts_validated_llm_semantic_cluster():
    class FakeLLMGateway:
        def generate_text(self, prompt_id, agent, input_data):
            return LLMGatewayResponse(
                prompt_id=prompt_id,
                provider="fake",
                model="fake-small-llm",
                output=(
                    '{"clusters":[{"sku":"SKU-SEM","issue":"Battery drain",'
                    '"review_count":1,"return_count":1,'
                    '"representative_evidence":["Review REV-SEM: Power dies quickly",'
                    '"Return RET-SEM: Does not hold charge"],"severity":"high"}],'
                    '"summary":"High-priority product issues detected for SKU-SEM."}'
                ),
            )

    payload = CustomerInsightAgentInput(
        context=AgentContext(
            run_id="customer-insight-llm-test",
            prompt_version="customer_insight_clustering_v1",
            created_at=datetime.now(timezone.utc),
        ),
        products=[
            Product(
                sku="SKU-SEM",
                name="VoltX Earbuds",
                category="Audio",
                brand="VoltX",
                price=2199,
                cost=1200,
            )
        ],
        reviews=[
            Review(
                review_id="REV-SEM",
                sku="SKU-SEM",
                rating=2,
                title="Power dies quickly",
                body="The earbuds stop working after one short call.",
                created_at=datetime.now(timezone.utc),
            )
        ],
        returns=[
            ProductReturn(
                return_id="RET-SEM",
                order_id="ORD-SEM",
                sku="SKU-SEM",
                reason=ReturnReason.quality_issue,
                notes="Does not hold charge.",
                created_at=datetime.now(timezone.utc),
            )
        ],
    )

    report, run_record = CustomerInsightAgent(llm_gateway=FakeLLMGateway()).run(payload)

    assert run_record.prompt_version == "customer_insight_clustering_v1"
    assert report.clusters[0].issue == "Battery drain"
    assert report.clusters[0].severity == RiskLevel.high


def test_customer_insight_agent_falls_back_when_llm_output_is_invalid():
    class BrokenLLMGateway:
        def generate_text(self, prompt_id, agent, input_data):
            return LLMGatewayResponse(
                prompt_id=prompt_id,
                provider="fake",
                model="fake-small-llm",
                output="not-json",
            )

    report, _ = CustomerInsightAgent(llm_gateway=BrokenLLMGateway()).run(create_customer_insight_input())

    assert len(report.clusters) == 2
    assert {cluster.issue for cluster in report.clusters} == {"Battery drain", "Size mismatch"}
