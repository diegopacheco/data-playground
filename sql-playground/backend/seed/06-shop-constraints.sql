ALTER TABLE shop.categories ADD CONSTRAINT categories_parent_fk FOREIGN KEY (parent_id) REFERENCES shop.categories (id);
ALTER TABLE shop.products ADD CONSTRAINT products_category_fk FOREIGN KEY (category_id) REFERENCES shop.categories (id);
ALTER TABLE shop.orders ADD CONSTRAINT orders_customer_fk FOREIGN KEY (customer_id) REFERENCES shop.customers (id);
ALTER TABLE shop.order_items ADD CONSTRAINT order_items_order_fk FOREIGN KEY (order_id) REFERENCES shop.orders (id);
ALTER TABLE shop.order_items ADD CONSTRAINT order_items_product_fk FOREIGN KEY (product_id) REFERENCES shop.products (id);
ALTER TABLE shop.payments ADD CONSTRAINT payments_order_fk FOREIGN KEY (order_id) REFERENCES shop.orders (id);
ALTER TABLE shop.reviews ADD CONSTRAINT reviews_product_fk FOREIGN KEY (product_id) REFERENCES shop.products (id);
ALTER TABLE shop.reviews ADD CONSTRAINT reviews_customer_fk FOREIGN KEY (customer_id) REFERENCES shop.customers (id);
