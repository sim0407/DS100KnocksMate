-- 教材CSVの投入（上流 docker/db/init/3_load.sql と同じ COPY ... CSV HEADER）
-- CSV はイメージ内 /opt/knocks/data に読み取り専用で配置される。

COPY customer FROM '/opt/knocks/data/customer.csv' WITH (FORMAT csv, HEADER true);
COPY category FROM '/opt/knocks/data/category.csv' WITH (FORMAT csv, HEADER true);
COPY product  FROM '/opt/knocks/data/product.csv'  WITH (FORMAT csv, HEADER true);
COPY receipt  FROM '/opt/knocks/data/receipt.csv'  WITH (FORMAT csv, HEADER true);
COPY store    FROM '/opt/knocks/data/store.csv'    WITH (FORMAT csv, HEADER true);
COPY geocode  FROM '/opt/knocks/data/geocode.csv'  WITH (FORMAT csv, HEADER true);

ANALYZE;
