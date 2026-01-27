#!/bin/bash
# scripts/entrypoint.sh - Docker entrypoint script for Jobs Service

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Starting Jobs Service...${NC}"

# Function to wait for a service to be ready
wait_for_service() {
    local host=$1
    local port=$2
    local service_name=$3
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}Waiting for $service_name to be ready...${NC}"

    while ! nc -z "$host" "$port"; do
        if [ $attempt -eq $max_attempts ]; then
            echo -e "${RED}$service_name is not available after $max_attempts attempts${NC}"
            exit 1
        fi
        echo "Attempt $attempt/$max_attempts: $service_name is not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo -e "${GREEN}$service_name is ready!${NC}"
}

# Parse database URL to extract host and port
if [ ! -z "$DATABASE_URL" ]; then
    # Extract host and port from DATABASE_URL
    DB_HOST=$(echo $DATABASE_URL | sed 's/.*@\([^:]*\):.*/\1/')
    DB_PORT=$(echo $DATABASE_URL | sed 's/.*:\([0-9]*\)\/.*/\1/')
elif [ ! -z "$DB_HOST" ] && [ ! -z "$DB_PORT" ]; then
    # Use environment variables
    echo "Using DB_HOST=$DB_HOST and DB_PORT=$DB_PORT"
else
    echo -e "${YELLOW}Database connection info not found, skipping database wait${NC}"
fi

# Parse Redis URL to extract host and port
if [ ! -z "$REDIS_URL" ]; then
    REDIS_HOST=$(echo $REDIS_URL | sed 's/redis:\/\/\([^:]*\):.*/\1/')
    REDIS_PORT=$(echo $REDIS_URL | sed 's/redis:\/\/[^:]*:\([0-9]*\).*/\1/')

    # Default Redis port if not specified
    if [ -z "$REDIS_PORT" ]; then
        REDIS_PORT=6379
    fi
else
    echo -e "${YELLOW}Redis connection info not found, skipping Redis wait${NC}"
fi

# Wait for database
if [ ! -z "$DB_HOST" ] && [ ! -z "$DB_PORT" ]; then
    wait_for_service "$DB_HOST" "$DB_PORT" "Database"
fi

# Wait for Redis
if [ ! -z "$REDIS_HOST" ] && [ ! -z "$REDIS_PORT" ]; then
    wait_for_service "$REDIS_HOST" "$REDIS_PORT" "Redis"
fi

# Wait for Users service (optional)
if [ ! -z "$USERS_SERVICE_URL" ]; then
    USERS_HOST=$(echo $USERS_SERVICE_URL | sed 's/http:\/\/\([^:]*\):.*/\1/')
    USERS_PORT=$(echo $USERS_SERVICE_URL | sed 's/http:\/\/[^:]*:\([0-9]*\).*/\1/')

    if [ ! -z "$USERS_HOST" ] && [ ! -z "$USERS_PORT" ]; then
        wait_for_service "$USERS_HOST" "$USERS_PORT" "Users Service"
    fi
fi

echo -e "${GREEN}All dependencies are ready!${NC}"

# Run database migrations
echo -e "${YELLOW}Running database migrations...${NC}"
python manage.py migrate --noinput

# Create cache table (if using database cache)
echo -e "${YELLOW}Creating cache table (if needed)...${NC}"
python manage.py createcachetable --dry-run > /dev/null 2>&1 && python manage.py createcachetable || echo "Cache table already exists or not needed"

# Collect static files (for production)
if [ "$DEBUG" = "False" ] || [ "$DEBUG" = "false" ] || [ "$ENVIRONMENT" = "production" ]; then
    echo -e "${YELLOW}Collecting static files...${NC}"
    python manage.py collectstatic --noinput
fi

# Seed initial data (only in development or if requested)
if [ "$ENVIRONMENT" = "development" ] || [ "$SEED_DATA" = "true" ]; then
    echo -e "${YELLOW}Seeding initial data...${NC}"
    python manage.py seed_data || echo "Data seeding skipped or failed"
fi

# Create superuser (only in development and if not exists)
if [ "$ENVIRONMENT" = "development" ] && [ ! -z "$DJANGO_SUPERUSER_USERNAME" ]; then
    echo -e "${YELLOW}Creating superuser (if not exists)...${NC}"
    python manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='$DJANGO_SUPERUSER_USERNAME').exists():
    User.objects.create_superuser('$DJANGO_SUPERUSER_USERNAME', '$DJANGO_SUPERUSER_EMAIL', '$DJANGO_SUPERUSER_PASSWORD')
    print('Superuser created successfully')
else:
    print('Superuser already exists')
" || echo "Superuser creation skipped"
fi

# Update job statistics (cleanup task)
if [ "$UPDATE_STATS_ON_START" = "true" ]; then
    echo -e "${YELLOW}Updating job statistics...${NC}"
    python manage.py update_job_stats || echo "Stats update skipped or failed"
fi

# Health check before starting
echo -e "${YELLOW}Performing health check...${NC}"
python manage.py check --deploy || echo "Health check warnings found"

echo -e "${GREEN}Jobs Service initialization completed!${NC}"

# Execute the main command
exec "$@"