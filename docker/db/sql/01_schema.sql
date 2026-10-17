-- 教材テーブル定義
-- 出典: 100knocks-preprocess docker/db/init/2_create_table.sh（MIT License, (c) 2020 The Japan DataScientist Society）
-- 上流の psql ヒアドキュメントから DDL 部分のみを抜き出したもの（列定義は無変更）。

CREATE TABLE customer(
  customer_id            VARCHAR(14),
  customer_name          VARCHAR(20),
  gender_cd              VARCHAR(1),
  gender                 VARCHAR(2),
  birth_day              DATE,
  age                    INTEGER,
  postal_cd              VARCHAR(8),
  address                VARCHAR(128),
  application_store_cd   VARCHAR(6),
  application_date       VARCHAR(8),
  status_cd              VARCHAR(12),
  PRIMARY KEY (customer_id)
);

CREATE TABLE category(
  category_major_cd     VARCHAR(2),
  category_major_name   VARCHAR(32),
  category_medium_cd    VARCHAR(4),
  category_medium_name  VARCHAR(32),
  category_small_cd     VARCHAR(6),
  category_small_name   VARCHAR(32),
  PRIMARY KEY (category_small_cd)
);

CREATE TABLE product(
  product_cd            VARCHAR(10),
  category_major_cd     VARCHAR(2),
  category_medium_cd    VARCHAR(4),
  category_small_cd     VARCHAR(6),
  unit_price            INTEGER,
  unit_cost             INTEGER,
  PRIMARY KEY (product_cd)
);

CREATE TABLE store(
  store_cd      VARCHAR(6),
  store_name    VARCHAR(128),
  prefecture_cd VARCHAR(2),
  prefecture    VARCHAR(5),
  address       VARCHAR(128),
  address_kana  VARCHAR(128),
  tel_no        VARCHAR(20),
  longitude     NUMERIC,
  latitude      NUMERIC,
  floor_area    NUMERIC,
  PRIMARY KEY (store_cd)
);

CREATE TABLE receipt(
  sales_ymd       INTEGER,
  sales_epoch     INTEGER,
  store_cd        VARCHAR(6),
  receipt_no      SMALLINT,
  receipt_sub_no  SMALLINT,
  customer_id     VARCHAR(14),
  product_cd      VARCHAR(10),
  quantity        INTEGER,
  amount          INTEGER,
  PRIMARY KEY (sales_ymd, store_cd, receipt_no, receipt_sub_no)
);

CREATE TABLE geocode(
  postal_cd       VARCHAR(8),
  prefecture      VARCHAR(4),
  city            VARCHAR(30),
  town            VARCHAR(30),
  street          VARCHAR(30),
  address         VARCHAR(30),
  full_address    VARCHAR(80),
  longitude       NUMERIC,
  latitude        NUMERIC
);
