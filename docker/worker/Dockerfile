# Pythonワーカー: 学習者のPythonコードを隔離実行する（内部ネットワーク専用）
#
# 依存の更新:  uv export --only-group worker --format requirements-txt --no-emit-project -o docker/worker/requirements.txt
#             uv export --only-group dev    --format requirements-txt --no-emit-project -o docker/worker/requirements-test.txt
FROM python:3.12.16-slim@sha256:8523d6abeb48ceae0b7240d30c5808fc26cb79c1a635bacdf19cf3baecfbec07 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # fork前にスレッドを作らない（fork後のデッドロック回避、CPU使用量の抑制）
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    KNOCKS_DATA_DIR=/opt/knocks/data \
    KNOCKS_WORKER_PORT=8000

WORKDIR /opt/knocks

# HTTPS の通信を検査するソフト（ウイルス対策ソフトの HTTPS スキャン、会社のプロキシ等）がある環境向け:
# docker/certs/*.crt に置いた証明書を追加で信頼する（起動用ファイルが必要に応じて PC の証明書を書き出す）
COPY docker/certs/ /usr/local/share/ca-certificates/knocks/
RUN update-ca-certificates >/dev/null
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY docker/worker/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# 教材データ（読み取り専用で使う）とアプリコード
COPY upstream/100knocks-preprocess/docker/work/data/*.csv /opt/knocks/data/
COPY core/__init__.py /opt/knocks/core/__init__.py
COPY core/execution/__init__.py core/execution/results.py /opt/knocks/core/execution/
COPY worker/ /opt/knocks/worker/

RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin knocks
USER 10001:10001

EXPOSE 8000
# サーバはシングルスレッドで実行中は /health に応答できないため、TCP接続の受付で判定する
HEALTHCHECK --interval=10s --timeout=5s --start-period=60s --retries=5 \
    CMD ["python", "-c", "import socket; socket.create_connection(('127.0.0.1', 8000), 3).close()"]
CMD ["python", "-m", "worker.server"]


# テスト用ステージ: docker build --target test ... && docker run --rm --init <image>
FROM base AS test
USER root
COPY docker/worker/requirements-test.txt /tmp/requirements-test.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-test.txt \
    && rm /tmp/requirements-test.txt
COPY pyproject.toml /opt/knocks/pyproject.toml
COPY tests/unit/test_worker_*.py /opt/knocks/tests/unit/
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/unit"]
