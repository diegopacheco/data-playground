DROP SCHEMA IF EXISTS social CASCADE;
CREATE SCHEMA social;
COMMENT ON SCHEMA social IS 'Small social network with posts, follows and view counters.';
CREATE TABLE social.users (id int PRIMARY KEY, handle text NOT NULL UNIQUE, joined_on date NOT NULL);
CREATE TABLE social.posts (id int PRIMARY KEY, author_id int NOT NULL REFERENCES social.users (id), body text NOT NULL, views bigint NOT NULL DEFAULT 0, created_at timestamptz NOT NULL);
CREATE TABLE social.post_views (id bigserial PRIMARY KEY, post_id int NOT NULL REFERENCES social.posts (id), viewed_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE social.follows (follower_id int REFERENCES social.users (id), followee_id int REFERENCES social.users (id), PRIMARY KEY (follower_id, followee_id), CHECK (follower_id <> followee_id));
CREATE TABLE social.hashtags (id int PRIMARY KEY, tag text NOT NULL UNIQUE);
CREATE TABLE social.post_hashtags (post_id int REFERENCES social.posts (id), hashtag_id int REFERENCES social.hashtags (id), PRIMARY KEY (post_id, hashtag_id));
CREATE TABLE social.trending (tag text PRIMARY KEY, score int NOT NULL);
COMMENT ON TABLE social.posts IS 'views is a denormalized counter, the hot row of the race.';
COMMENT ON TABLE social.post_views IS 'Append only view events, the source of truth for the counter.';
COMMENT ON TABLE social.trending IS 'Feed from an external trends API, joined by tag text.';
INSERT INTO social.users VALUES (1, 'ana', '2024-01-01'), (2, 'ben', '2024-02-01'), (3, 'cris', '2024-03-01'), (4, 'dani', '2024-04-01'), (5, 'edu', '2024-05-01'), (6, 'fabi', '2025-01-01');
INSERT INTO social.posts VALUES
 (1, 1, 'Postgres 18 is out', 0, now() - interval '3 days'),
 (2, 1, 'Async IO in practice', 0, now() - interval '2 days'),
 (3, 2, 'Why I left the ORM', 0, now() - interval '2 days'),
 (4, 3, 'SKIP LOCKED queues', 0, now() - interval '1 day'),
 (5, 4, 'Hello world', 0, now() - interval '5 hours');
INSERT INTO social.post_views (post_id, viewed_at)
SELECT p, now() - (d * interval '1 day') - (g * interval '1 hour')
FROM (VALUES (2, 0, 3), (2, 1, 2), (3, 1, 4), (3, 2, 1), (4, 0, 2)) v (p, d, n)
CROSS JOIN LATERAL generate_series(1, v.n) g;
UPDATE social.posts p SET views = (SELECT count(*) FROM social.post_views v WHERE v.post_id = p.id);
INSERT INTO social.follows VALUES (1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (4, 1), (5, 2), (6, 3), (5, 6);
INSERT INTO social.hashtags VALUES (1, 'postgres'), (2, 'performance'), (3, 'orm'), (4, 'queues'), (5, 'rust');
INSERT INTO social.post_hashtags VALUES (1, 1), (2, 1), (2, 2), (3, 3), (4, 1), (4, 4);
INSERT INTO social.trending VALUES ('postgres', 98), ('ai', 97), ('rust', 80), ('kubernetes', 60);
