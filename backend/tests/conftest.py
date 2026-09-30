import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base, get_db
from app.main import app
import app.main as main_module

@pytest.fixture
def client(monkeypatch):
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    TestingSession=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
    monkeypatch.setattr(main_module,"engine",engine)
    def override_db():
        db=TestingSession()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db]=override_db
    try:
        with TestClient(app) as test_client:
            assert inspect(engine).has_table("schedules")
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine); engine.dispose()
