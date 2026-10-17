# アプリ（Streamlit UI・採点・進捗保存・SQL実行の呼び出し）。学習者のPythonコードはここで実行しない。
#
# 依存の更新:  uv export --only-group app --format requirements-txt --no-emit-project -o docker/app/requirements.txt
FROM python:3.12.13-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /opt/knocks

COPY docker/app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

COPY .streamlit/ /opt/knocks/.streamlit/
COPY core/ /opt/knocks/core/
COPY app/ /opt/knocks/app/
COPY exercises/ /opt/knocks/exercises/

# 学習履歴（SQLite）は名前付きvolumeに置く。volume初期化時に所有者を引き継がせるため先に作成
RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin knocks \
    && mkdir -p /var/lib/knocks \
    && chown 10001:10001 /var/lib/knocks
ENV HOME=/tmp \
    KNOCKS_PROGRESS_DB=/var/lib/knocks/progress.sqlite3
USER 10001:10001

EXPOSE 8501
HEALTHCHECK --interval=10s --timeout=5s --start-period=30s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"]
# コンテナ内では全インターフェースで待ち受け、ホストへの公開は compose で 127.0.0.1 に限定する
CMD ["streamlit", "run", "app/main.py", "--server.address=0.0.0.0"]


# 統合テスト用ステージ（compose の tests サービスから DB・ワーカーに接続して実行）
FROM base AS test
USER root
COPY docker/worker/requirements-test.txt /tmp/requirements-test.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-test.txt \
    && rm /tmp/requirements-test.txt
COPY pyproject.toml /opt/knocks/pyproject.toml
# 参照結果を上流Notebookの保存出力と照合するテスト用（本番イメージには含めない）
COPY upstream/100knocks-preprocess/docker/work/answer/ /opt/knocks/upstream/100knocks-preprocess/docker/work/answer/
COPY tests/ /opt/knocks/tests/
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "integration", "tests/integration"]
