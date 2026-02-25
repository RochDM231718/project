import json
import os
import logging
from contextvars import ContextVar

current_locale = ContextVar("current_locale", default="en")

logger = logging.getLogger(__name__)


class TranslationManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TranslationManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.translations_dir = os.path.join(base_dir, 'translations')

        self.translations = {
            'en': self._load_translations('en.json'),
            'ru': self._load_translations('ru.json')
        }

        self._initialized = True

    def _load_translations(self, filename):
        path = os.path.join(self.translations_dir, filename)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error("Failed to load translation %s: %s", filename, e)
                return {}
        else:
            logger.warning("Translation file not found: %s", path)
            return {}

    def gettext(self, key, replacements=None, locale=None, **kwargs):
        if not locale:
            locale = current_locale.get()

        dictionary = self.translations.get(locale, self.translations.get('en', {}))
        text = dictionary.get(key, key)

        if replacements is None:
            replacements = kwargs
        else:
            replacements.update(kwargs)

        if replacements:
            try:
                return text.format(**replacements)
            except KeyError:
                return text
        return text

    def get_supported_locales(self):
        return list(self.translations.keys())