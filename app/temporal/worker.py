import asyncio

from app.config import settings
from app.database.init_db import init_database
from app.temporal.activities import (
    build_daily_report_activity,
    run_customer_insight_activity,
    run_daily_ops_activity,
    run_inventory_activity,
    run_marketing_activity,
    run_pricing_activity,
)


async def connect_temporal_once():
    from temporalio.client import Client

    return await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )


async def connect_temporal_with_retry(max_attempts: int = 30, delay_seconds: float = 2.0):
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await connect_temporal_once()
        except Exception as exc:
            last_error = exc
            print(
                f"Temporal connect attempt {attempt}/{max_attempts} failed: {exc}",
                flush=True,
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay_seconds)
    raise RuntimeError(
        f"Unable to connect to Temporal at {settings.temporal_address} "
        f"after {max_attempts} attempts"
    ) from last_error


async def main() -> None:
    from temporalio.worker import Worker

    from app.temporal.workflows import DailyOpsTemporalWorkflow

    init_database()
    client = await connect_temporal_with_retry()
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[DailyOpsTemporalWorkflow],
        activities=[
            run_inventory_activity,
            run_customer_insight_activity,
            run_pricing_activity,
            run_marketing_activity,
            build_daily_report_activity,
            run_daily_ops_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
