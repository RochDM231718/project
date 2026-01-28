from app.infrastructure.database.connection import db_instance
from app.seeders.users_table_seeder import UsersTableSeeder


async def seed():
    print("Seeding database...")

    async with db_instance.session_factory() as db:
        try:
            await UsersTableSeeder.run(db)
            print("Database seeded successfully!")
        except Exception as e:
            print(f"Error seeding database: {e}")
