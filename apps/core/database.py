from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from google.cloud.sql.connector import Connector, IPTypes
from apps.core.config import settings

def get_engine():
    connector = Connector()

    instance_connection_name = (
        f"{settings.project_id}:{settings.region}:{settings.instance_id}"
    )

    def getconn():
        conn = connector.connect(
            instance_connection_string=instance_connection_name,
            driver="pg8000",
            user=settings.db_user,
            password=settings.db_password,
            db=settings.db_name,
            ip_type=IPTypes.PUBLIC
        )
        return conn

    engine = create_engine(
        "postgresql+pg8000://",
        creator=getconn,
    )
    return engine

engine = get_engine()

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# test the connection
# from sqlalchemy import text
# if __name__ == "__main__":
#     try:
#         with engine.connect() as conn:
#             result = conn.execute(text("SELECT count(*) from users"))
#             print("✅ Connection successful:", result.fetchone())
#     except Exception as e:
#         print("❌ Connection failed:", e)