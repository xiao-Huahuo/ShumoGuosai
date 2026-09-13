"""问题四冻结参数、原子写入与可复现配置。"""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import os

CODE_ROOT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("Q4_WORKSPACE_ROOT", str(CODE_ROOT.parents[1]))).resolve()
SOURCE = ROOT / "docs/4/Q4_问题四_严格因果波动电价_完整建模_最终修订版.md"
ATTACHMENTS = ROOT / "docs/CUMCM2026Problems/C题/附件"
Q2_RUN = ROOT / "outputs/q2/dispatch_runs/20260911_224501"

DT = 1 / 6
CAP = 5000 * DT
E_MIN, E_MAX, E_INITIAL = 1200.0, 10800.0, 6000.0
ETA_C = ETA_D = 0.9
NODES = (0, 6, 12, 18)
TOL = 1e-5


@dataclass(frozen=True)
class Config:
    """未由方案定值的计算参数全部显式保留在审计中。"""

    scenarios: int = 20
    residual_window: int = 56
    net_weight: float = 0.5
    bootstrap_repetitions: int = 100
    bootstrap_quantile: float = 0.95
    dro_scale: float = 1.0
    conditional: bool = True
    joint: bool = True
    min_ess: float = 10.0
    nodes: tuple[int, ...] = NODES
    seconds: float = 30.0
    gap: float = 0.03
    solver_threads: int = 4
    seed: int = 20250913
    allow_limited: bool = False

    def __post_init__(self) -> None:
        if self.scenarios < 1:
            raise ValueError("场景数必须为正")
        if self.residual_window not in (56, 84, 112):
            raise ValueError("残差窗口只能取方案规定的56/84/112日")
        if not 0 < self.net_weight < 1:
            raise ValueError("联合距离权重必须位于(0,1)")
        if self.bootstrap_repetitions < 1 or not 0 < self.bootstrap_quantile < 1:
            raise ValueError("bootstrap设置非法")
        if self.dro_scale < 0 or self.min_ess <= 0:
            raise ValueError("鲁棒半径倍率或ESS阈值非法")
        if self.nodes not in ((0,), (0, 6), (0, 6, 12), NODES):
            raise ValueError("更新时间集合必须为方案四种之一")
        if self.seconds <= 0 or not 0 <= self.gap < 1 or self.solver_threads < 1:
            raise ValueError("求解预算非法")

    def signature(self) -> str:
        payload = SOURCE.read_bytes() + json.dumps(asdict(self), sort_keys=True).encode("utf-8")
        for source in sorted(CODE_ROOT.glob("*.py")):
            if not source.name.startswith("test_"):
                payload += source.name.encode("utf-8") + source.read_bytes()
        return hashlib.sha256(payload).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.pending")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def write_csv(path: Path, frame: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.pending")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        frame.to_csv(stream, index=False, float_format="%.17g")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)

