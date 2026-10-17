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

COPY core/ /opt/knocks/core/
COPY exercises/ /opt/knocks/exercises/

RUN useradd --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin knocks
USER 10001:10001

# UIはPhase 1で追加する
CMD ["python", "-c", "print('app: UI is not implemented yet (Phase 1)')"]


# 統合テスト用ステージ（compose の tests サービスから DB・ワーカーに接続して実行）
FROM base AS test
USER root
COPY docker/worker/requirements-test.txt /tmp/requirements-test.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-test.txt \
    && rm /tmp/requirements-test.txt
COPY pyproject.toml /opt/knocks/pyproject.toml
COPY tests/ /opt/knocks/tests/
USER 10001:10001
CMD ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-m", "integration", "tests/integration"]
