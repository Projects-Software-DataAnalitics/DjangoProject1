#!/bin/bash

# Script to sync JSON data to PostgreSQL
# Make sure you have .env file with DB_PASSWORD set

cd "$(dirname "$0")"

echo "Syncing data from JSON files to PostgreSQL..."
echo ""
echo "Make sure you have a .env file in DjangoProject1/ with:"
echo "  DB_NAME=djangoproject2"
echo "  DB_USER=postgres"
echo "  DB_PASSWORD=your_password"
echo "  DB_HOST=localhost"
echo "  DB_PORT=5432"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "WARNING: .env file not found!"
    echo "Creating a template .env file..."
    cat > .env << EOF
DB_NAME=djangoproject2
DB_USER=postgres
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=5432
EOF
    echo ".env file created. Please edit it and add your PostgreSQL password."
    exit 1
fi

# Run the sync command
python3 manage.py sync_from_json

