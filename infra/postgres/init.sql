-- Runs once when the local Postgres container is first created.
-- aibos      owns the schema and runs migrations.
-- aibos_app  is what the API connects as. It is not the table owner and not a
--            superuser, so row-level security applies to every query it makes.
create role aibos_app login password 'aibos_app' nosuperuser nobypassrls;
create database aibos_test owner aibos;
