-- Open Door's database on the shared portfolio Postgres server. Run once, as the server's init
-- superuser, connected to `postgres`, with OD_OWNER_PASSWORD in psql's environment. The
-- password is sent once; password_encryption (scram-sha-256) stores only its verifier.
\set ON_ERROR_STOP on
\getenv od_owner_password OD_OWNER_PASSWORD
CREATE ROLE opendoor_owner LOGIN CREATEROLE PASSWORD :'od_owner_password';
CREATE DATABASE opendoor OWNER opendoor_owner;
REVOKE CONNECT ON DATABASE opendoor FROM PUBLIC;
\connect opendoor
CREATE EXTENSION IF NOT EXISTS vector;
