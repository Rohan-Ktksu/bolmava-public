-- Separate role and database for the destructive test suite; the test role cannot connect to the app database.
CREATE ROLE bolmava_test LOGIN PASSWORD 'bolmava_test';
CREATE DATABASE bolmava_test OWNER bolmava_test;
REVOKE CONNECT ON DATABASE bolmava FROM PUBLIC;
