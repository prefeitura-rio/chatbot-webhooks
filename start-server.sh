#!/usr/bin/env bash
# Run migrations
(cd /app; python manage.py migrate)
# Start gunicorn in background
(cd /app; gunicorn chatbot_webhooks.wsgi --user www-data --bind 0.0.0.0:8000 --workers 3 --log-level debug --timeout 180) &
# Locks until gunicorn is up
while ! nc -z localhost 8000; do
echo "Waiting for gunicorn server to start...";
sleep 1;
done;
# Start nginx in foreground
echo "Starting nginx server..."
nginx -g "daemon off;"
