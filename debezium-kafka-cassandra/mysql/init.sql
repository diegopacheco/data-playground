CREATE DATABASE IF NOT EXISTS sales;
USE sales;
CREATE TABLE orders (
  order_id INT PRIMARY KEY,
  customer VARCHAR(100) NOT NULL,
  product VARCHAR(100) NOT NULL,
  category VARCHAR(50) NOT NULL,
  quantity INT NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  ts VARCHAR(32) NOT NULL
);
LOAD DATA INFILE '/docker-entrypoint-initdb.d/orders.csv' INTO TABLE orders FIELDS TERMINATED BY ',' LINES TERMINATED BY '\n' IGNORE 1 LINES (order_id, customer, product, category, quantity, price, ts);
CREATE USER 'debezium'@'%' IDENTIFIED BY 'debezium';
GRANT SELECT, RELOAD, SHOW DATABASES, REPLICATION SLAVE, REPLICATION CLIENT ON *.* TO 'debezium'@'%';
CREATE USER 'app'@'%' IDENTIFIED BY 'app';
GRANT SELECT, INSERT, UPDATE, DELETE ON sales.* TO 'app'@'%';
FLUSH PRIVILEGES;
