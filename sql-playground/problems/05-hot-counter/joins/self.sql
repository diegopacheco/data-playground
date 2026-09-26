SELECT a.handle AS user_a, b.handle AS user_b
FROM social.follows f1
JOIN social.follows f2 ON f2.follower_id = f1.followee_id AND f2.followee_id = f1.follower_id
JOIN social.users a ON a.id = f1.follower_id
JOIN social.users b ON b.id = f1.followee_id
WHERE f1.follower_id < f1.followee_id;
