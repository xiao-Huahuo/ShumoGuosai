"""题设参数、v4冻结协议及用户确认的终端标定口径。"""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'docs/3/Q3_第三问_最终建模_严格修订终稿_v4.md'
ATTACHMENTS = ROOT / 'docs/CUMCM2026Problems/C题/附件'
DT, CAP, E_MIN, E_MAX, E_INITIAL, ETA = 1/6, 5000/6, 1200., 10800., 6000., .9
NODES = (0, 6, 12, 18)
TOL = 1e-5


@dataclass(frozen=True)
class Config:
    scenarios: int = 20
    tail: int = 2
    unconditional: bool = False
    terminal_scale: float = 1.
    interpolation: str = 'linear'
    feedback: str = 'aggregate'
    settlement: str = 'final'
    nodes: tuple[int, ...] = NODES
    deterministic: bool = False
    # 数值预算不改变数学模型；正式默认求证至数值最优，限时不通过则停止。
    seconds: float = 120.
    gap: float = 0.
    fd_delta: float = 100.
    fd_base: float = E_INITIAL
    fd_days: int = 28

    def __post_init__(self) -> None:
        if self.scenarios < 1 or not 0 <= self.tail <= self.scenarios:
            raise ValueError('场景/尾部数非法')
        if self.nodes not in ((0,), (0, 6), (0, 6, 12), NODES):
            raise ValueError('更新时间集合必须为方案四种之一')
        if self.interpolation not in ('linear', 'pchip') or self.feedback not in ('aggregate', 'lag'):
            raise ValueError('插值或反馈口径非法')
        if self.settlement not in ('final', 'sequential') or self.seconds <= 0 or not 0 <= self.gap < 1:
            raise ValueError('结算或求解设置非法')
        if not 0 < self.fd_delta <= E_MAX-self.fd_base or self.terminal_scale <= 0:
            raise ValueError('终端标定参数非法')

    def signature(self) -> str:
        return hashlib.sha256(SOURCE.read_bytes()+json.dumps(asdict(self), sort_keys=True).encode('utf-8')).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.pending')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def write_csv(path: Path, frame: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding='utf-8', float_format='%.17g')
