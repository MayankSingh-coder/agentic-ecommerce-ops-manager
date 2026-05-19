from pathlib import Path
import json

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_dockerfile_builds_fastapi_runtime_image():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "FROM python:3.11-slim" in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert 'CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]' in dockerfile


def test_docker_compose_contains_api_worker_temporal_and_postgres_services():
    compose = yaml.safe_load((PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    assert {"api", "temporal-worker", "postgres", "temporal", "temporal-ui", "litellm"}.issubset(services)
    assert services["api"]["ports"] == ["8000:8000"]
    assert services["api"]["environment"]["DATABASE_URL"].startswith("postgresql+psycopg://")
    assert services["api"]["environment"]["LITELLM_API_KEY"] == "${LITELLM_API_KEY:-sk-local-litellm}"
    assert services["temporal-worker"]["command"] == ["python", "-m", "app.temporal.worker"]
    assert services["temporal-worker"]["restart"] == "on-failure"
    assert services["temporal-worker"]["depends_on"]["api"]["condition"] == "service_healthy"
    assert services["litellm"]["ports"] == ["4000:4000"]
    assert "./litellm_config.yaml:/app/config.yaml:ro" in services["litellm"]["volumes"]
    assert services["temporal"]["environment"]["DB"] == "postgres12"
    assert "DYNAMIC_CONFIG_FILE_PATH" not in services["temporal"]["environment"]
    assert services["temporal"]["restart"] == "on-failure"
    assert services["temporal"]["ports"] == ["7233:7233"]
    assert services["temporal-ui"]["ports"] == ["8080:8080"]


def test_env_example_documents_required_runtime_settings():
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "DATABASE_URL=postgresql+psycopg://ecommerce_ops:ecommerce_ops@postgres:5432/ecommerce_ops" in env_example
    assert "ECOMMERCE_OPS_API_KEY=change-me" in env_example
    assert "LITELLM_API_KEY=sk-local-litellm" in env_example
    assert "OPENAI_API_KEY=" in env_example
    assert "TEMPORAL_ADDRESS=temporal:7233" in env_example
    assert "TEMPORAL_TASK_QUEUE=ecommerce-ops-task-queue" in env_example
    assert "python-dotenv==" in requirements


def test_fastapi_app_uses_lifespan_not_deprecated_startup_event():
    main_source = (PROJECT_ROOT / "app/main.py").read_text(encoding="utf-8")

    assert "@app.on_event" not in main_source
    assert "async def lifespan" in main_source
    assert "lifespan=lifespan" in main_source


def test_litellm_config_maps_prompt_model_aliases_to_provider_models():
    config = yaml.safe_load((PROJECT_ROOT / "litellm_config.yaml").read_text(encoding="utf-8"))
    model_names = {model["model_name"] for model in config["model_list"]}
    provider_models = {
        model["model_name"]: model["litellm_params"]["model"]
        for model in config["model_list"]
    }

    assert "deterministic-summary-v1" in model_names
    assert "deterministic-marketing-v1" in model_names
    assert "deterministic-customer-insight-v1" in model_names
    assert provider_models["deterministic-summary-v1"] == "gemini/gemini-2.5-flash"
    assert provider_models["deterministic-marketing-v1"] == "gemini/gemini-2.5-flash-lite"
    assert provider_models["deterministic-customer-insight-v1"] == "gemini/gemini-2.5-flash-lite"
    assert config["general_settings"]["master_key"] == "os.environ/LITELLM_MASTER_KEY"


def test_postman_collection_contains_demo_api_requests():
    collection_path = PROJECT_ROOT / "docs/api/ecommerce-ops.postman_collection.json"
    collection = json.loads(collection_path.read_text(encoding="utf-8"))

    def flatten_items(items):
        flattened = []
        for item in items:
            if "item" in item:
                flattened.extend(flatten_items(item["item"]))
            else:
                flattened.append(item)
        return flattened

    requests = flatten_items(collection["item"])
    urls = {request["request"]["url"] for request in requests}

    assert collection["info"]["schema"].endswith("collection/v2.1.0/collection.json")
    assert len(requests) >= 25
    assert "{{base_url}}/api/v1/ecommerce-ops/workflows/daily-ops/run" in urls
    assert "{{base_url}}/api/v1/ecommerce-ops/workflows/daily-ops/temporal/start" in urls
    assert "{{base_url}}/api/v1/ecommerce-ops/reviews" in urls
    assert "{{base_url}}/api/v1/ecommerce-ops/inventory/SKU-1003" in urls
