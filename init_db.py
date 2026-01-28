import asyncio
from app.infrastructure.database import engine, Base
# Import ALL your models here so SQLAlchemy knows about them
from app.models.user import Users
from app.models.achievement import Achievement


async def init_models():
    async with engine.begin() as conn:
        # This drops tables if they exist (optional, good for dev reset)
        # await conn.run_sync(Base.metadata.drop_all)

        # This creates the tables
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created successfully!")


if __name__ == "__main__":
    asyncio.run(init_models())