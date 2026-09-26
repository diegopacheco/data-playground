SELECT h.tag AS our_tag, t.tag AS trending_tag, t.score
FROM social.hashtags h
FULL OUTER JOIN social.trending t ON t.tag = h.tag
ORDER BY t.score DESC NULLS LAST, h.tag;
