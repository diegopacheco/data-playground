CREATE USER openmetadata_user WITH PASSWORD 'openmetadata_password';
CREATE DATABASE openmetadata_db OWNER openmetadata_user;
CREATE USER om_reader WITH PASSWORD 'om_reader_password';
CREATE DATABASE shop;
