CREATE UNIQUE INDEX customers_email_key ON shop.customers (email);
CREATE UNIQUE INDEX products_sku_key ON shop.products (sku);
CREATE INDEX products_category_idx ON shop.products (category_id);
CREATE INDEX orders_customer_idx ON shop.orders (customer_id);
CREATE INDEX orders_created_at_idx ON shop.orders (created_at);
CREATE INDEX order_items_order_idx ON shop.order_items (order_id);
CREATE UNIQUE INDEX payments_order_key ON shop.payments (order_id);
CREATE INDEX reviews_product_idx ON shop.reviews (product_id);
