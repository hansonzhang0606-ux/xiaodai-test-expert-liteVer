import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = SKILL_ROOT / "sql" / "upgrade_v5.8_to_v5.9.sql"


class SqlUpgradeV59Tests(unittest.TestCase):
    def test_upgrade_is_idempotent_and_additive_only(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        upper_sql = sql.upper()

        self.assertIn("information_schema.COLUMNS", sql)
        self.assertIn("ai_estimated_time_saved_hours", sql)
        self.assertIn("DECIMAL(10,2) NULL", sql)
        self.assertIn("PREPARE", upper_sql)
        self.assertNotIn("DROP TABLE", upper_sql)
        self.assertNotIn("DROP COLUMN", upper_sql)
        self.assertNotIn("TRUNCATE", upper_sql)

    def test_upgrade_does_not_choose_a_database_or_embed_credentials(self):
        sql = SQL_PATH.read_text(encoding="utf-8")
        upper_sql = sql.upper()

        self.assertNotIn("USE ", upper_sql)
        self.assertNotIn("PASSWORD", upper_sql)
        self.assertIn("DATABASE()", upper_sql)


if __name__ == "__main__":
    unittest.main()

