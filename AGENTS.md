# AGENTS

## Purpose

This repository is being migrated to a Duo ORM-native database architecture.
The goal is not a partial wrapper or compatibility layer as the final state.
The goal is to make this repo behave as if its database layer had originally
been scaffolded around Duo ORM, while preserving the current migration history
and the existing database state.

This document defines the technical contract for that migration.

## Scope

Duo ORM should own:

- database bootstrap
- model base and model definitions
- schema mapping for DB-facing Pydantic schemas
- Alembic metadata ownership
- migration workflow

This repository will still keep its FastAPI endpoints, services, adapters,
Redis logic, and application-specific business flows. Duo ORM is the database
foundation, not a replacement for the application layer.

## High-Level Goal

End state:

- `app/db/database.py` is the canonical database owner
- all ORM models inherit from the Duo ORM-managed base
- `app/db/schemas` contains model-adjacent Pydantic schemas
- Alembic is wired to Duo-managed metadata
- future migrations are generated and run against the Duo-managed model graph
- legacy database helpers are removed once the cutover is complete

## Current Constraint

The existing migration history must be preserved first.

That means the initial migration to Duo ORM must keep the current Alembic
identity stable before any cleanup or normalization work is done.

## Non-Negotiable Migration Contract

These items must remain stable during the first cutover:

- existing revision files
- existing `revision` and `down_revision` chain
- existing Alembic version table name
- existing applied migration history in the database

Files may be moved or reorganized if needed, but the migration lineage itself
must remain intact.

## Version Table Rule

The current repository uses the existing Alembic version-table contract.
During the first migration to Duo ORM, preserve that version table instead of
switching immediately to a Duo default naming scheme.

Reason:

- preserving the current version table preserves the current database history
- changing the version table introduces an avoidable migration-state cutover

If a future cleanup wants to rename the version table, treat that as a
separate, explicit migration step after the Duo ORM cutover is stable.

## Metadata Ownership Rule

Alembic must ultimately point to Duo-managed metadata.

Target end state:

- Alembic loads metadata from the shared Duo-managed `db` object
- model imports are centralized so the metadata graph is complete at migration
  time

Initial bridge step:

- update the Alembic environment to preserve current migration identity while
  switching `target_metadata` to the Duo-managed model base

## Alembic Import Rule

The Alembic environment must import every model module before resolving
`target_metadata`.

Required outcome:

- `app/db/models/__init__.py` imports all model modules that contribute tables
- Alembic resolves a complete metadata graph at migration time

If a model is not imported, Alembic may incorrectly detect dropped tables or
missing schema objects.

## Canonical Database Owner

`app/db/database.py` becomes the single source of truth for:

- database URL binding
- sync engine ownership
- async engine ownership
- session access
- shared model base

The rest of the repository should consume that module rather than owning
independent database bootstrap logic.

## Legacy Files

These files are transitional and should not remain as final architecture:

- `app/db/models/base_model.py`
- `app/config/postgres.py`

They may exist temporarily during the migration, but the intended end state is:

- `app/db/models/base_model.py` removed
- `app/config/postgres.py` removed

Do not delete them until all dependent imports and behaviors have been moved
onto the Duo ORM-backed database layer.

## Models

Target model rules:

- models live under `app/db/models`
- models inherit from the Duo-managed model base
- relationships remain standard SQLAlchemy relationships where needed
- existing table names should remain stable unless there is a deliberate schema
  migration for renaming

Model migration should favor preserving current database compatibility first.
Aesthetic cleanup can happen later.

## Table Name Rule

During the initial Duo ORM cutover, existing `__tablename__` values must remain
stable.

Do not rely on inferred table names if doing so could change the current table
contract.

If table names are ever changed, that must happen through an explicit schema
migration, not as a side effect of rebasing models onto Duo ORM.

## Column Semantics Rule

During the initial Duo ORM cutover, column semantics must remain equivalent to
the current schema.

Preserve:

- column types
- nullability
- primary keys
- foreign keys
- unique constraints
- indexes
- server defaults
- update/default timestamp behavior

Important:

- do not silently replace a `server_default` with only a Python-side default
- do not change constraint behavior while changing metadata ownership
- do not change relationship-backed foreign-key structure unless it is part of
  an explicit migration

## Schemas

`app/db/schemas` should be populated and treated as the canonical home for
database-adjacent Pydantic schemas.

Recommended schema pattern:

- one namespace class per model
- nested `Create`, `Update`, and `Read` Pydantic models

Example convention:

- `Client.Create`
- `Client.Update`
- `Client.Read`

This aligns with Duo ORM schema-mapping helpers and keeps model-adjacent schema
definitions organized.

## Migration Workflow

Preferred migration sequence:

1. Introduce Duo-managed `app/db/database.py`.
2. Rebase model ownership onto the Duo-managed base.
3. Update Alembic environment to use Duo-managed metadata while preserving the
   current version-table contract and revision history.
4. Normalize the migration layout only after the current history is preserved.
5. Remove legacy DB bootstrap and base-model code once all imports are cut over.

## Migration Layout Policy

Layout changes are allowed if they do not break migration identity.

Safe to change:

- file locations
- import paths
- Alembic environment implementation

Unsafe to change during the first cutover:

- revision identifiers
- `down_revision` lineage
- current version-table contract

## First Autogenerate Rule

The first Alembic autogenerate after the Duo ORM cutover should produce either:

- no changes
- or only intentional, reviewed changes

If autogenerate proposes unexpected table drops, column rewrites, constraint
changes, or default changes, treat that as a metadata mismatch and fix the
model/Alembic wiring before generating new migrations.

The first post-cutover migration is a validation step. It is not the place for
unintended schema drift.

## Service Layer Policy

The service layer does not need to be rewritten simply because the database
foundation is changing.

Allowed:

- keep FastAPI routes, services, adapters, and Redis logic structurally intact
- update only the parts that touch models, sessions, metadata, or migrations

Goal:

- database ownership changes
- application behavior remains stable

## Final Architecture Standard

This repository should eventually look like a Duo ORM-driven application with:

- Duo-managed database bootstrap
- Duo-managed models
- Duo-managed schema mapping
- Duo-managed Alembic metadata
- preserved historical migrations

Temporary hybrid states are acceptable only during migration. They are not the
desired end state.
