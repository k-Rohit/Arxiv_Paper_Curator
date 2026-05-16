.PHONY: help start stop restart status logs health setup format lint test test-cov clean

start:
    docker compose up --build -d

stop:
    docker compose down

status:
    docker compose ps

logs:
    docker compose logs -f

health:
    curl http://localhost:8000/api/v1/health
