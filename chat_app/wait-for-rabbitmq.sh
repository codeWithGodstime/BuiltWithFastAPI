# #!/bin/bash
# # wait-for-db.sh

# # This script waits for a database to be available on a given host and port.

# # Variables for the database host and port.
# # Replace with your actual database host and port, e.g., "db" and "5432" for a PostgreSQL container.
# HOST="rabbitmq"
# PORT="5672"
# TIMEOUT=60

# echo "Waiting for ${HOST}:${PORT} to be available..."

# # Loop until the host and port are reachable or until the timeout is reached.
# while ! nc -z $HOST $PORT >/dev/null 2>&1; do
#   echo "Still waiting..."
#   sleep 1
#   TIMEOUT=$((TIMEOUT - 1))
#   if [ $TIMEOUT -eq 0 ]; then
#     echo "Error: Timeout reached. Could not connect to ${HOST}:${PORT}."
#     exit 1
#   fi
# done

# echo "${HOST}:${PORT} is ready. Starting application..."

# # Execute the main command passed to this script (e.g., the uvicorn command).
exec "$@"