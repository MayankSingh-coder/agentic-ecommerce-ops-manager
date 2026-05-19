import json

from app.evals.runner import EvalRunner


def main() -> None:
    results = EvalRunner().run_all()
    print(json.dumps([result.model_dump(mode="json") for result in results], indent=2))
    if not all(result.passed for result in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
