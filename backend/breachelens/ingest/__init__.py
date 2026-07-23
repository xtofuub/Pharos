"""Ingest pipeline package.

Modules are intentionally not imported eagerly. This keeps lightweight helpers such
as the folder scanner usable without initializing the database, auth stack, or
parser dependencies.
"""
