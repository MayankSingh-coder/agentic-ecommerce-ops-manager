from app.evals.contracts import EvalAssertions, EvalCase, EvalSuite
from app.evals.runner import EvalRunner


def test_eval_runner_loads_registered_eval_suites():
    runner = EvalRunner()

    assert runner.list_suite_ids() == [
        "daily_ops_summary_eval_v1",
        "marketing_draft_eval_v1",
    ]


def test_eval_runner_passes_current_prompt_eval_suites():
    results = EvalRunner().run_all()

    assert all(result.passed for result in results)
    assert all(result.score >= result.min_score for result in results)
    assert {result.prompt_id for result in results} == {
        "daily_ops_summary_v1",
        "marketing_draft_v1",
    }


def test_eval_runner_reports_missing_required_output():
    suite = EvalSuite(
        suite_id="failing_eval_v1",
        prompt_id="marketing_draft_v1",
        agent="marketing",
        min_score=1.0,
        cases=[
            EvalCase(
                case_id="missing_required",
                input={"product_name": "Trail Runner", "offer": "10% off"},
                assertions=EvalAssertions(
                    required_substrings=["this phrase does not exist"],
                    forbidden_substrings=[],
                ),
            )
        ],
    )

    result = EvalRunner().run_suite(suite)

    assert result.passed is False
    assert result.score == 0
    assert result.case_results[0].missing_required == ["this phrase does not exist"]
