# 0001. Postgres with pgvector, not MongoDB

Status: Accepted · Date: 2026-09-29

## Context

The owner's earlier Employee Management System stored everything in MongoDB: one document of about
fifty fields per employee, dates as strings, and no indexes. Open Door's data is relational at its
core. Reporting lines are recursive, approvals relate people to requests, permissions are joins,
and every row belongs to a tenant.

## Decision

Postgres 17 with the pgvector extension, through SQLAlchemy 2 (async) and Alembic migrations.

## Rejected alternatives

- **MongoDB:** tenant isolation would have to be repeated in every query instead of enforced by the
  database, and the relational queries (a manager's indirect reports, a request and its approver)
  fight the document model.
- **A separate vector database (Chroma, Qdrant):** a second system to run, and "search only the
  handbook sections that apply to this person" would span two stores instead of one query.

## Consequences

Row-level security becomes available (see 0003). Migrations are explicit and checked for drift in
CI. The owner's portfolio shows range: Folio uses Mongo with a separate vector store; Open Door uses
Postgres for both.
