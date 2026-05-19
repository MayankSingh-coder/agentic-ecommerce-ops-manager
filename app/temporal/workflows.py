from datetime import timedelta

from temporalio import workflow


@workflow.defn(name="DailyOpsTemporalWorkflow")
class DailyOpsTemporalWorkflow:
    @workflow.run
    async def run(self, request_payload: dict) -> dict:
        inventory = await workflow.execute_activity(
            "run_inventory_activity",
            request_payload,
            start_to_close_timeout=timedelta(minutes=5),
        )
        customer_insight = await workflow.execute_activity(
            "run_customer_insight_activity",
            request_payload,
            start_to_close_timeout=timedelta(minutes=5),
        )
        pricing = await workflow.execute_activity(
            "run_pricing_activity",
            request_payload,
            start_to_close_timeout=timedelta(minutes=5),
        )
        marketing = await workflow.execute_activity(
            "run_marketing_activity",
            {
                "request": request_payload,
                "channels": request_payload.get("channels", ["email"]),
                "inventory_recommendations": inventory["recommendations"],
                "customer_insights": customer_insight["report"],
            },
            start_to_close_timeout=timedelta(minutes=5),
        )
        return await workflow.execute_activity(
            "build_daily_report_activity",
            {
                "request": request_payload,
                "inventory": inventory,
                "customer_insight": customer_insight,
                "pricing": pricing,
                "marketing": marketing,
            },
            start_to_close_timeout=timedelta(minutes=5),
        )
