import os
import unittest
from unittest.mock import patch

from app.config import AppEnvironment, ConfigurationError, get_api_settings, get_database_settings


class DatabaseSettingsTests(unittest.TestCase):
    def tearDown(self):
        get_database_settings.cache_clear()
        get_api_settings.cache_clear()

    def load_with(self, environment):
        get_database_settings.cache_clear()
        with patch("app.config._load_backend_env"), patch.dict(
            os.environ, environment, clear=True
        ):
            return get_database_settings()

    def test_database_url_takes_precedence(self):
        settings = self.load_with(
            {
                "DATABASE_URL": "postgresql://example.test/tradevalue",
                "ENV": "nonprod",
                "DB_USER": "ignored",
                "DB_NAME": "ignored",
                "DB_CONNECT_TIMEOUT": "7",
            }
        )

        self.assertEqual(
            settings.database_url, "postgresql://example.test/tradevalue"
        )
        self.assertEqual(settings.environment, AppEnvironment.NONPROD)
        self.assertEqual(settings.connect_timeout_seconds, 7)

    def test_component_settings_are_url_encoded(self):
        settings = self.load_with(
            {
                "ENV": "dev",
                "DB_USER": "trade value",
                "DB_PASSWORD": "secret/@word",
                "DB_HOST": "localhost",
                "DB_PORT": "5433",
                "DB_NAME": "hockey data",
            }
        )

        self.assertEqual(
            settings.database_url,
            "postgresql://trade%20value:secret%2F%40word@localhost:5433/"
            "hockey%20data",
        )

    def test_missing_database_settings_are_rejected(self):
        with self.assertRaisesRegex(ConfigurationError, "DATABASE_URL"):
            self.load_with({"ENV": "prod"})

    def test_scoped_url_matches_selected_environment(self):
        settings = self.load_with(
            {
                "ENV": "prod",
                "PROD_DATABASE_URL": "postgresql://prod.test/tradevalue",
                "NONPROD_DATABASE_URL": "postgresql://nonprod.test/tradevalue",
                "DATABASE_URL": "postgresql://fallback.test/tradevalue",
            }
        )

        self.assertEqual(
            settings.database_url, "postgresql://prod.test/tradevalue"
        )

    def test_environment_is_required_and_validated(self):
        with self.assertRaisesRegex(ConfigurationError, "ENV must be one of"):
            self.load_with({"DATABASE_URL": "postgresql://example.test/db"})

    def test_api_cors_origins_are_trimmed(self):
        get_api_settings.cache_clear()
        with patch("app.config._load_backend_env"), patch.dict(
            os.environ,
            {"CORS_ORIGINS": "https://trade.example, https://preview.example"},
            clear=True,
        ):
            settings = get_api_settings()
        self.assertEqual(
            settings.cors_origins,
            ("https://trade.example", "https://preview.example"),
        )


if __name__ == "__main__":
    unittest.main()
