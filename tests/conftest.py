"""テスト全体の設定。

本番のワーカーと同じく、数値計算ライブラリのスレッド数を1にしてから numpy 等を読み込む
（docker/worker/Dockerfile と同じ）。スレッドがあるプロセスで fork すると、子プロセスが
デッドロックしうるため（worker/sandbox.py のテストで必要）。
"""

import os

for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_name, "1")
