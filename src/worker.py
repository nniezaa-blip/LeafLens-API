"""Cloudflare Worker entrypoint for the Lextari API."""

from workers import asgi

from app.main import app

Default = asgi.entrypoint(app)
