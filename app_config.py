from pathlib import Path

import yaml

APPLICATION_CONFIG_PATH = Path(__file__).resolve().with_name("application.yml")


class AppConfigError(Exception):
    """Raised when the application config cannot be loaded."""


def load_application_config() -> dict:
    try:
        with APPLICATION_CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file) or {}
    except FileNotFoundError as exc:
        raise AppConfigError(
            f"Missing application config file: {APPLICATION_CONFIG_PATH}"
        ) from exc
    except yaml.YAMLError as exc:
        raise AppConfigError("application.yml is not valid YAML.") from exc

    if not isinstance(config, dict):
        raise AppConfigError("application.yml must contain a top-level mapping.")

    return config


def get_openrouter_default_model() -> str:
    config = load_application_config()
    openrouter_config = config.get("openrouter")
    if not isinstance(openrouter_config, dict):
        raise AppConfigError("application.yml is missing the 'openrouter' section.")

    default_model = openrouter_config.get("default_model")
    if not isinstance(default_model, str) or not default_model.strip():
        raise AppConfigError(
            "application.yml is missing 'openrouter.default_model'."
        )

    return default_model.strip()
