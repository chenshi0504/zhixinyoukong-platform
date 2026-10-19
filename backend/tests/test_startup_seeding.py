"""
Regression tests for startup seeding behavior.
"""
import pytest


class TestStartupSeeding:
    @pytest.mark.asyncio
    async def test_lifespan_seeds_default_users_for_file_db(self, monkeypatch):
        from app import main as main_module

        calls = {"init": 0, "seed": 0, "closed": 0}

        def fake_init_db():
            calls["init"] += 1

        class DummyDB:
            def close(self):
                calls["closed"] += 1

        def fake_session_local():
            return DummyDB()

        def fake_seed_data(db):
            calls["seed"] += 1

        monkeypatch.setattr(main_module, "init_db", fake_init_db)
        monkeypatch.setattr(main_module, "SessionLocal", fake_session_local)
        monkeypatch.setattr(main_module, "seed_data", fake_seed_data)
        monkeypatch.setattr(main_module.settings, "DATABASE_URL", "sqlite:///seed-test.db")

        async with main_module.lifespan(main_module.app):
            pass

        assert calls == {"init": 1, "seed": 1, "closed": 1}

    @pytest.mark.asyncio
    async def test_lifespan_skips_seed_for_memory_db(self, monkeypatch):
        from app import main as main_module

        calls = {"init": 0, "seed": 0}

        def fake_init_db():
            calls["init"] += 1

        def fake_seed_data(db):
            calls["seed"] += 1

        monkeypatch.setattr(main_module, "init_db", fake_init_db)
        monkeypatch.setattr(main_module, "seed_data", fake_seed_data)
        monkeypatch.setattr(main_module.settings, "DATABASE_URL", "sqlite:///:memory:")

        async with main_module.lifespan(main_module.app):
            pass

        assert calls == {"init": 1, "seed": 0}
