import importlib


def get_channel_prompt(channel: str, task: str) -> str:
    module_path = f"channels.{channel}.prompts.{task}"
    try:
        module = importlib.import_module(module_path)
        return module.build_prompt()
    except (ImportError, AttributeError) as e:
        raise ValueError(
            f"Impossible de charger le prompt '{task}' pour la chaîne '{channel}': {e}"
        ) from e