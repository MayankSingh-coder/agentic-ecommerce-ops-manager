from pathlib import Path

import yaml

from app.evals.contracts import EvalCase, EvalCaseResult, EvalSuite, EvalSuiteResult
from app.llm.gateway import LLMGateway


class EvalRunner:
    def __init__(
        self,
        eval_dir: str | Path = "evals",
        llm_gateway: LLMGateway | None = None,
    ) -> None:
        if eval_dir == "evals":
            self.eval_dir = Path(__file__).resolve().parents[2] / "evals"
        else:
            self.eval_dir = Path(eval_dir)
        self.llm_gateway = llm_gateway or LLMGateway()

    def list_suite_ids(self) -> list[str]:
        return [suite.suite_id for suite in self.load_suites()]

    def load_suites(self) -> list[EvalSuite]:
        suites: list[EvalSuite] = []
        for path in sorted(self.eval_dir.glob("*.yaml")):
            with path.open("r", encoding="utf-8") as eval_file:
                suites.append(EvalSuite(**yaml.safe_load(eval_file)))
        return suites

    def run_all(self) -> list[EvalSuiteResult]:
        return [self.run_suite(suite) for suite in self.load_suites()]

    def run_suite(self, suite: EvalSuite) -> EvalSuiteResult:
        case_results = [self._run_case(suite, eval_case) for eval_case in suite.cases]
        score = sum(result.score for result in case_results) / len(case_results)
        return EvalSuiteResult(
            suite_id=suite.suite_id,
            prompt_id=suite.prompt_id,
            passed=score >= suite.min_score and all(result.passed for result in case_results),
            score=score,
            min_score=suite.min_score,
            case_results=case_results,
        )

    def _run_case(self, suite: EvalSuite, eval_case: EvalCase) -> EvalCaseResult:
        response = self.llm_gateway.generate_text(
            prompt_id=suite.prompt_id,
            agent=suite.agent,
            input_data=eval_case.input,
        )
        output = response.output
        missing_required = [
            value
            for value in eval_case.assertions.required_substrings
            if value not in output
        ]
        found_forbidden = [
            value
            for value in eval_case.assertions.forbidden_substrings
            if value in output
        ]
        total_assertions = (
            len(eval_case.assertions.required_substrings)
            + len(eval_case.assertions.forbidden_substrings)
        )
        failed_assertions = len(missing_required) + len(found_forbidden)
        score = 1.0 if total_assertions == 0 else (total_assertions - failed_assertions) / total_assertions
        return EvalCaseResult(
            suite_id=suite.suite_id,
            case_id=eval_case.case_id,
            prompt_id=suite.prompt_id,
            passed=not missing_required and not found_forbidden,
            score=score,
            missing_required=missing_required,
            found_forbidden=found_forbidden,
            output=output,
        )
