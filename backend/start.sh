#!/usr/bin/env bash
gunicorn --bind 0.0.0.0:10000 --workers 1 --threads 8 --timeout 0 app:app