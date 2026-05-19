from collections import defaultdict
from datetime import datetime, timezone
import json
from typing import Dict, List

from app.llm.gateway import LLMGateway
from app.security.text_sanitizer import sanitize_untrusted_text

from ..contracts import (
    AgentName,
    AgentRunRecord,
    AgentRunStatus,
    CustomerInsightAgentInput,
    CustomerInsightReport,
    IssueCluster,
    RiskLevel,
)
from ..schemas import ProductReturn, ReturnReason, Review


class CustomerInsightAgent:
    name = AgentName.customer_insight
    prompt_version = "customer_insight_clustering_v1"
    input_schema = "CustomerInsightAgentInput.v1"
    output_schema = "CustomerInsightReport.v1"

    def __init__(self, llm_gateway: LLMGateway | None = None) -> None:
        self.llm_gateway = llm_gateway or LLMGateway()

    def run(self, payload: CustomerInsightAgentInput) -> tuple[CustomerInsightReport, AgentRunRecord]:
        started_at = datetime.now(timezone.utc)
        report = self._build_llm_report(payload)
        completed_at = datetime.now(timezone.utc)
        run_record = AgentRunRecord(
            run_id=payload.context.run_id,
            agent_name=self.name,
            status=AgentRunStatus.succeeded,
            prompt_version=self.prompt_version,
            input_schema=self.input_schema,
            output_schema=self.output_schema,
            started_at=started_at,
            completed_at=completed_at,
        )
        return report, run_record

    def _build_llm_report(self, payload: CustomerInsightAgentInput) -> CustomerInsightReport:
        try:
            response = self.llm_gateway.generate_text(
                prompt_id=self.prompt_version,
                agent=self.name.value,
                input_data=self._llm_input(payload),
            )
            report = CustomerInsightReport.model_validate(json.loads(response.output))
            report = self._sanitize_and_validate_llm_report(report, payload)
            if report.clusters:
                return report
        except Exception:
            pass

        clusters = self._build_rule_clusters(payload.reviews, payload.returns)
        return CustomerInsightReport(
            clusters=clusters,
            summary=self._summary(clusters),
        )

    def _llm_input(self, payload: CustomerInsightAgentInput) -> dict:
        product_names = {product.sku: product.name for product in payload.products}
        return {
            "lookback_days": payload.lookback_days,
            "products": [
                {
                    "sku": product.sku,
                    "name": product.name,
                    "category": product.category,
                    "brand": product.brand,
                }
                for product in payload.products
            ],
            "reviews": [
                {
                    "review_id": review.review_id,
                    "sku": review.sku,
                    "product_name": product_names.get(review.sku),
                    "rating": review.rating,
                    "title": sanitize_untrusted_text(review.title),
                    "body": sanitize_untrusted_text(review.body),
                }
                for review in payload.reviews
            ],
            "returns": [
                {
                    "return_id": product_return.return_id,
                    "sku": product_return.sku,
                    "product_name": product_names.get(product_return.sku),
                    "reason": product_return.reason.value,
                    "notes": sanitize_untrusted_text(product_return.notes or ""),
                }
                for product_return in payload.returns
            ],
            "output_contract": {
                "clusters": [
                    {
                        "sku": "string",
                        "issue": "short semantic issue label",
                        "review_count": "integer >= 0",
                        "return_count": "integer >= 0",
                        "representative_evidence": ["sanitized review/return references only"],
                        "severity": "low | medium | high | critical",
                    }
                ],
                "summary": "short evidence-backed summary",
            },
        }

    def _sanitize_and_validate_llm_report(
        self,
        report: CustomerInsightReport,
        payload: CustomerInsightAgentInput,
    ) -> CustomerInsightReport:
        valid_skus = {product.sku for product in payload.products}
        valid_review_ids = {review.review_id for review in payload.reviews}
        valid_return_ids = {product_return.return_id for product_return in payload.returns}
        clusters: list[IssueCluster] = []
        for cluster in report.clusters:
            if cluster.sku not in valid_skus:
                continue
            evidence = [
                sanitize_untrusted_text(item)
                for item in cluster.representative_evidence
                if any(reference_id in item for reference_id in valid_review_ids | valid_return_ids)
            ][:3]
            clusters.append(
                IssueCluster(
                    sku=cluster.sku,
                    issue=cluster.issue.strip()[:80],
                    review_count=cluster.review_count,
                    return_count=cluster.return_count,
                    representative_evidence=evidence,
                    severity=cluster.severity,
                )
            )
        return CustomerInsightReport(
            clusters=clusters,
            summary=sanitize_untrusted_text(report.summary),
        )

    def _build_rule_clusters(
        self,
        reviews: List[Review],
        returns: List[ProductReturn],
    ) -> List[IssueCluster]:
        review_counts: Dict[tuple[str, str], int] = defaultdict(int)
        return_counts: Dict[tuple[str, str], int] = defaultdict(int)
        evidence: Dict[tuple[str, str], List[str]] = defaultdict(list)

        for review in reviews:
            issue = self._classify_review(review)
            if issue is None:
                continue
            key = (review.sku, issue)
            review_counts[key] += 1
            evidence[key].append(f"Review {review.review_id}: {sanitize_untrusted_text(review.title)}")

        for product_return in returns:
            issue = self._classify_return(product_return)
            key = (product_return.sku, issue)
            return_counts[key] += 1
            if product_return.notes:
                evidence[key].append(
                    f"Return {product_return.return_id}: {sanitize_untrusted_text(product_return.notes)}"
                )

        all_keys = sorted(set(review_counts) | set(return_counts))
        return [
            IssueCluster(
                sku=sku,
                issue=issue,
                review_count=review_counts[(sku, issue)],
                return_count=return_counts[(sku, issue)],
                representative_evidence=evidence[(sku, issue)][:3],
                severity=self._severity(
                    review_count=review_counts[(sku, issue)],
                    return_count=return_counts[(sku, issue)],
                ),
            )
            for sku, issue in all_keys
        ]

    def _classify_review(self, review: Review) -> str | None:
        text = f"{review.title} {review.body}".lower()
        if any(term in text for term in ["size", "sizing", "exchange", "bigger", "small"]):
            return "Size mismatch"
        if any(term in text for term in ["battery", "drain", "last", "charge"]):
            return "Battery drain"
        if any(term in text for term in ["damaged", "broken", "packaging"]):
            return "Damaged packaging"
        if review.rating <= 2:
            return "Low rating"
        return None

    def _classify_return(self, product_return: ProductReturn) -> str:
        if product_return.reason == ReturnReason.size_mismatch:
            return "Size mismatch"
        if product_return.reason == ReturnReason.quality_issue:
            notes = (product_return.notes or "").lower()
            if any(term in notes for term in ["battery", "drain", "charge"]):
                return "Battery drain"
            return "Quality issue"
        if product_return.reason == ReturnReason.damaged:
            return "Damaged packaging"
        if product_return.reason == ReturnReason.late_delivery:
            return "Late delivery"
        return "Other return reason"

    def _severity(self, *, review_count: int, return_count: int) -> RiskLevel:
        weighted_score = review_count + (return_count * 2)
        if weighted_score >= 8:
            return RiskLevel.critical
        if weighted_score >= 3:
            return RiskLevel.high
        if weighted_score >= 2:
            return RiskLevel.medium
        return RiskLevel.low

    def _summary(self, clusters: List[IssueCluster]) -> str:
        if not clusters:
            return "No material product issues detected from reviews or returns."
        high_priority = [
            cluster
            for cluster in clusters
            if cluster.severity in {RiskLevel.high, RiskLevel.critical}
        ]
        if high_priority:
            skus = ", ".join(cluster.sku for cluster in high_priority)
            return f"High-priority product issues detected for {skus}."
        return "Product issues detected, but current evidence is low severity."
