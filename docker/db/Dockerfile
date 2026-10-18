# 教材用PostgreSQL。初期化（スキーマ作成・CSV投入・ロール設定）をビルド時に済ませ、
# 起動を速くし、コンテナを作り直せば常に元の状態に戻るようにする。教材DBに永続ボリュームは使わない。
FROM postgres:18.6-trixie@sha256:74935e72241653ca55e0414067e6d8763aceb8a810eb51b452253ec3dcfc4336

# 上流と同じ ja_JP.UTF-8（日本語の並び順・メッセージ）
RUN sed -i -E 's/^# (ja_JP.UTF-8 UTF-8)/\1/' /etc/locale.gen && locale-gen
ENV LANG=ja_JP.utf8 \
    # 公式イメージの VOLUME 外に置き、初期化済みデータをイメージに含める
    PGDATA=/var/lib/knocks/pgdata

COPY --chown=postgres:postgres upstream/100knocks-preprocess/docker/work/data/*.csv /opt/knocks/data/
COPY --chown=postgres:postgres docker/db/sql/ /opt/knocks/sql/
COPY --chown=postgres:postgres docker/db/pg_hba.conf /opt/knocks/pg_hba.conf

RUN mkdir -p /var/lib/knocks && chown postgres:postgres /var/lib/knocks
USER postgres
RUN initdb --locale=ja_JP.UTF-8 --encoding=UTF8 --auth-local=peer --auth-host=scram-sha-256 -D "$PGDATA" \
    && pg_ctl -D "$PGDATA" -o "-c listen_addresses=''" -w start \
    && createdb dsdojo_db \
    && psql -v ON_ERROR_STOP=1 -d dsdojo_db \
        -f /opt/knocks/sql/01_schema.sql \
        -f /opt/knocks/sql/02_load.sql \
        -f /opt/knocks/sql/03_roles.sql \
    && pg_ctl -D "$PGDATA" -m fast -w stop \
    && cp /opt/knocks/pg_hba.conf "$PGDATA/pg_hba.conf" \
    && echo "listen_addresses = '*'" >> "$PGDATA/postgresql.conf"

HEALTHCHECK --interval=5s --timeout=5s --start-period=30s --retries=20 \
    CMD ["pg_isready", "-h", "/var/run/postgresql", "-d", "dsdojo_db"]
CMD ["postgres"]
