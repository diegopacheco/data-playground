AUDIT (
  name assert_non_negative
);

SELECT *
FROM @this_model
WHERE @column < 0
