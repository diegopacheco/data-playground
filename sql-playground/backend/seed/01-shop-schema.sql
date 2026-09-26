CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
DROP SCHEMA IF EXISTS shop CASCADE;
CREATE SCHEMA shop;
COMMENT ON SCHEMA shop IS 'Online store with 5M order lines used to practice joins, plans and indexing.';

CREATE TABLE shop.categories (
  id smallint PRIMARY KEY,
  parent_id smallint,
  name text NOT NULL UNIQUE
);
COMMENT ON TABLE shop.categories IS 'Product taxonomy. Top level categories have no parent, sub categories point to their parent.';
COMMENT ON COLUMN shop.categories.id IS 'Category identifier.';
COMMENT ON COLUMN shop.categories.parent_id IS 'Parent category, NULL for a top level category.';
COMMENT ON COLUMN shop.categories.name IS 'Unique display name.';

CREATE TABLE shop.customers (
  id bigint PRIMARY KEY,
  email text NOT NULL,
  full_name text NOT NULL,
  country char(2) NOT NULL,
  city text NOT NULL,
  tier text NOT NULL CHECK (tier IN ('bronze', 'silver', 'gold', 'platinum')),
  marketing_opt_in boolean NOT NULL,
  created_at timestamptz NOT NULL
);
COMMENT ON TABLE shop.customers IS 'People who registered in the store. 250k rows.';
COMMENT ON COLUMN shop.customers.id IS 'Customer identifier.';
COMMENT ON COLUMN shop.customers.email IS 'Login email, unique, stored lower case.';
COMMENT ON COLUMN shop.customers.full_name IS 'First and last name.';
COMMENT ON COLUMN shop.customers.country IS 'ISO 3166 alpha-2 country code. Not indexed on purpose.';
COMMENT ON COLUMN shop.customers.city IS 'City of the shipping address.';
COMMENT ON COLUMN shop.customers.tier IS 'Loyalty tier: bronze, silver, gold or platinum.';
COMMENT ON COLUMN shop.customers.marketing_opt_in IS 'True when the customer accepted marketing emails.';
COMMENT ON COLUMN shop.customers.created_at IS 'Registration time.';

CREATE TABLE shop.products (
  id integer PRIMARY KEY,
  category_id smallint NOT NULL,
  sku text NOT NULL,
  name text NOT NULL,
  price numeric(10,2) NOT NULL CHECK (price > 0),
  stock integer NOT NULL CHECK (stock >= 0),
  active boolean NOT NULL,
  created_at timestamptz NOT NULL
);
COMMENT ON TABLE shop.products IS 'Catalog of sellable items. 25k rows.';
COMMENT ON COLUMN shop.products.id IS 'Product identifier. Lower ids are the best sellers.';
COMMENT ON COLUMN shop.products.category_id IS 'Sub category the product belongs to.';
COMMENT ON COLUMN shop.products.sku IS 'Stock keeping unit, unique.';
COMMENT ON COLUMN shop.products.name IS 'Display name.';
COMMENT ON COLUMN shop.products.price IS 'Current list price in USD.';
COMMENT ON COLUMN shop.products.stock IS 'Units available in the warehouse.';
COMMENT ON COLUMN shop.products.active IS 'False when the product is no longer sold.';
COMMENT ON COLUMN shop.products.created_at IS 'Time the product was listed.';

CREATE TABLE shop.orders (
  id bigint PRIMARY KEY,
  customer_id bigint NOT NULL,
  status text NOT NULL CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled')),
  total numeric(12,2) NOT NULL,
  item_count integer NOT NULL,
  created_at timestamptz NOT NULL,
  shipped_at timestamptz
);
COMMENT ON TABLE shop.orders IS 'Checkout of a customer. 1.5M rows, ids grow with created_at.';
COMMENT ON COLUMN shop.orders.id IS 'Order identifier, increases with time.';
COMMENT ON COLUMN shop.orders.customer_id IS 'Customer who placed the order.';
COMMENT ON COLUMN shop.orders.status IS 'pending, paid, shipped, delivered or cancelled. Not indexed on purpose.';
COMMENT ON COLUMN shop.orders.total IS 'Sum of quantity * unit_price of its lines.';
COMMENT ON COLUMN shop.orders.item_count IS 'Number of lines in the order.';
COMMENT ON COLUMN shop.orders.created_at IS 'Checkout time.';
COMMENT ON COLUMN shop.orders.shipped_at IS 'Time the parcel left the warehouse, NULL when not shipped.';

CREATE TABLE shop.order_items (
  id bigint PRIMARY KEY,
  order_id bigint NOT NULL,
  product_id integer NOT NULL,
  quantity integer NOT NULL CHECK (quantity > 0),
  unit_price numeric(10,2) NOT NULL
);
COMMENT ON TABLE shop.order_items IS 'Lines of every order. 5M rows, the biggest table.';
COMMENT ON COLUMN shop.order_items.id IS 'Line identifier.';
COMMENT ON COLUMN shop.order_items.order_id IS 'Order the line belongs to.';
COMMENT ON COLUMN shop.order_items.product_id IS 'Product sold. Not indexed on purpose.';
COMMENT ON COLUMN shop.order_items.quantity IS 'Units bought.';
COMMENT ON COLUMN shop.order_items.unit_price IS 'Price paid per unit at checkout time.';

CREATE TABLE shop.payments (
  id bigint PRIMARY KEY,
  order_id bigint NOT NULL,
  method text NOT NULL CHECK (method IN ('card', 'pix', 'paypal', 'bank_transfer', 'gift_card')),
  status text NOT NULL CHECK (status IN ('approved', 'refunded', 'chargeback')),
  amount numeric(12,2) NOT NULL,
  paid_at timestamptz NOT NULL
);
COMMENT ON TABLE shop.payments IS 'Money received for an order. One payment per paid order.';
COMMENT ON COLUMN shop.payments.id IS 'Payment identifier.';
COMMENT ON COLUMN shop.payments.order_id IS 'Order paid, unique.';
COMMENT ON COLUMN shop.payments.method IS 'card, pix, paypal, bank_transfer or gift_card.';
COMMENT ON COLUMN shop.payments.status IS 'approved, refunded or chargeback.';
COMMENT ON COLUMN shop.payments.amount IS 'Amount captured in USD.';
COMMENT ON COLUMN shop.payments.paid_at IS 'Capture time. Not indexed on purpose.';

CREATE TABLE shop.reviews (
  id bigint PRIMARY KEY,
  product_id integer NOT NULL,
  customer_id bigint NOT NULL,
  rating smallint NOT NULL CHECK (rating BETWEEN 1 AND 5),
  title text NOT NULL,
  created_at timestamptz NOT NULL
);
COMMENT ON TABLE shop.reviews IS 'Ratings left by customers on delivered products.';
COMMENT ON COLUMN shop.reviews.id IS 'Review identifier.';
COMMENT ON COLUMN shop.reviews.product_id IS 'Product reviewed.';
COMMENT ON COLUMN shop.reviews.customer_id IS 'Author of the review. Not indexed on purpose.';
COMMENT ON COLUMN shop.reviews.rating IS 'Stars from 1 to 5.';
COMMENT ON COLUMN shop.reviews.title IS 'Short headline of the review.';
COMMENT ON COLUMN shop.reviews.created_at IS 'Time the review was posted.';
