SELECT setseed(0.42);
INSERT INTO shop.categories (id, parent_id, name)
SELECT g, NULL, (ARRAY['Electronics','Home','Books','Sports','Toys','Fashion','Beauty','Grocery'])[g]
FROM generate_series(1, 8) g;
INSERT INTO shop.categories (id, parent_id, name)
SELECT 8 + (p - 1) * 4 + s, p,
       (ARRAY['Electronics','Home','Books','Sports','Toys','Fashion','Beauty','Grocery'])[p] || ' / ' ||
       (ARRAY['Essentials','Premium','Outlet','Kids'])[s]
FROM generate_series(1, 8) p CROSS JOIN generate_series(1, 4) s;

INSERT INTO shop.customers (id, email, full_name, country, city, tier, marketing_opt_in, created_at)
SELECT g,
       'customer' || g || '@mail.test',
       (ARRAY['Ana','Bruno','Carla','Diego','Elena','Felipe','Gina','Hugo','Iris','Joao','Kate','Lucas','Maya','Noah','Olga','Pedro'])[1 + (g * 7) % 16] || ' ' ||
       (ARRAY['Silva','Santos','Smith','Garcia','Muller','Rossi','Dubois','Kowalski','Tanaka','Nguyen','Oliveira','Jones'])[1 + (g * 13) % 12],
       c.country,
       c.city,
       CASE WHEN r < 0.62 THEN 'bronze' WHEN r < 0.88 THEN 'silver' WHEN r < 0.97 THEN 'gold' ELSE 'platinum' END,
       random() < 0.35,
       timestamptz '2021-01-01' + (g / 250000.0) * interval '1800 days'
FROM (SELECT g, random() AS r, floor(power(random(), 1.6) * 12)::int AS k FROM generate_series(1, 250000) g) x
CROSS JOIN LATERAL (
  SELECT (ARRAY['BR','US','DE','PT','FR','ES','IT','GB','CA','MX','JP','AR'])[x.k + 1] AS country,
         (ARRAY['Sao Paulo','New York','Berlin','Lisbon','Paris','Madrid','Rome','London','Toronto','Mexico City','Tokyo','Buenos Aires'])[x.k + 1] AS city
) c;

INSERT INTO shop.products (id, category_id, sku, name, price, stock, active, created_at)
SELECT g,
       9 + (g * 11) % 32,
       'SKU-' || lpad(g::text, 6, '0'),
       (ARRAY['Smart','Classic','Eco','Ultra','Mini','Pro','Soft','Rapid'])[1 + g % 8] || ' ' ||
       (ARRAY['Lamp','Phone','Novel','Ball','Robot','Jacket','Serum','Coffee','Chair','Watch'])[1 + (g / 8) % 10] || ' ' || g,
       round((4.99 + random() * 495)::numeric, 2),
       floor(random() * 500)::int,
       random() > 0.08,
       timestamptz '2020-06-01' + random() * interval '1900 days'
FROM generate_series(1, 25000) g;
