-- 学習者用の読み取り専用ロール
-- 安全性はSQL文字列の検査ではなく、権限・読み取り専用トランザクション・タイムアウトで担保する。
-- パスワードは秘密情報ではない（DBはDocker内部ネットワーク専用でホストに公開せず、ロールは読み取り専用）。

CREATE ROLE knocks_learner
  LOGIN PASSWORD 'knocks-learner-readonly'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS
  CONNECTION LIMIT 8;

-- PUBLIC が既定で持つ CONNECT / TEMPORARY を外し、必要な権限だけを付与
REVOKE ALL ON DATABASE dsdojo_db FROM PUBLIC;
GRANT CONNECT ON DATABASE dsdojo_db TO knocks_learner;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO knocks_learner;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO knocks_learner;

-- アプリ側でも BEGIN READ ONLY / statement_timeout を設定するが、ロール既定値としても固定する
ALTER ROLE knocks_learner SET default_transaction_read_only = on;
ALTER ROLE knocks_learner SET statement_timeout = '15s';
ALTER ROLE knocks_learner SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE knocks_learner SET temp_file_limit = '512MB';
ALTER ROLE knocks_learner SET work_mem = '32MB';
