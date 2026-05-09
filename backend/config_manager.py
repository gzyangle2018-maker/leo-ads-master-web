"""
Leo Ads Master - Config Manager
Handles app settings including OpenAI API key and analysis thresholds.
"""
import os
import json
import sys


def get_app_dir() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ConfigManager:
    def __init__(self):
        base_dir = get_app_dir()
        self.config_file = os.path.join(base_dir, 'data', 'app_config.json')
        os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
        self._config = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return self._defaults()

    def _defaults(self) -> dict:
        return {
            'openai_api_key': '',
            'openai_base_url': 'https://api.openai.com/v1',
            'openai_model': 'gpt-4o',
            'analysis_language': 'zh',
            'budget_limit_pct': 10,
            'acos_target': 25,
            'tacos_target': 12,
            'auto_export_excel': True,
            'theme': 'dark',
            'version': '2.1.0',
            'llm_provider': 'openai',
            'llm_api_key': '',
            'llm_base_url': '',
            'llm_model': '',
            'llm_temperature': 0.7,
            'llm_max_tokens': 2000,
        }

    def save(self):
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self._config, f, ensure_ascii=False, indent=2)

    def get(self, key: str, default=None):
        return self._config.get(key, default)

    def set(self, key: str, value):
        self._config[key] = value
        self.save()

    def all(self) -> dict:
        return self._config.copy()
