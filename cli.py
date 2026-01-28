import typer
import uvicorn
import os
import asyncio
from app.seeders.main import seed as seed_db

app = typer.Typer()


@app.command()
def run(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = True
):
    """Run the FastAPI server"""
    uvicorn.run("main:app", host=host, port=port, reload=reload, env_file=".env")

@app.command()
def migrate(message: str = "Auto-generated migration"):
    """Create and apply migrations"""
    os.system(f'alembic revision --autogenerate -m "{message}"')
    os.system('alembic upgrade head')

@app.command()
def makemigrations(message: str = "New migration"):
    """Create a new migration file"""
    os.system(f'alembic revision --autogenerate -m "{message}"')

@app.command()
def rollback():
    """Rollback the last migration"""
    os.system('alembic downgrade -1')

@app.command()
def seed():
    """Run database seeders"""
    asyncio.run(seed_db())

@app.command()
def install():
    """Install dependencies"""
    os.system('pip install -r requirements.txt')

@app.command()
def update():
    """Update project from git"""
    os.system('git pull')
    os.system('pip install -r requirements.txt')
    os.system('alembic upgrade head')

if __name__ == "__main__":
    app()