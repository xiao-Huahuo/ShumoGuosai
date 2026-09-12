"""求解精度的显式执行修订；不改变已冻结的预测协议和准备库。"""

import hashlib
import json
import math
from pathlib import Path

from protocol import PROTOCOL, signature


def execution_settings(run):
    path = Path(run)/"raw/solver_precision_revision.json"
    if not path.exists():
        return {}
    raw = path.read_bytes()
    revision = json.loads(raw)
    gap = revision["solver_gap"]
    if (revision["parent_protocol_sha256"] != signature() or not revision.get("authorization")
            or isinstance(gap, bool) or not isinstance(gap, (int, float))
            or not math.isfinite(gap) or not PROTOCOL["solver_gap"] <= gap < 1):
        raise ValueError("求解精度修订缺少授权、父协议不符或门槛无效")
    return {"solver_gap": float(gap), "execution_revision": hashlib.sha256(raw).hexdigest()}
