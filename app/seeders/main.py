from app.infrastructure.database import async_session_maker
from app.seeders.users_table_seeder import UsersTableSeeder


async def seed():
    print("Seeding database...")

    # Используем async_session_maker, который мы импортировали из database/__init__.py
    async with async_session_maker() as db:
        try:
            await UsersTableSeeder.run(db)
            print("Database seeded successfully!")
        except Exception as e:
            print(f"Error seeding database: {e}")