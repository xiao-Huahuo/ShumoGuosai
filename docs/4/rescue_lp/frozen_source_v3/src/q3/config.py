"""题设参数、v4冻结协议及用户确认的终端标定口径。"""
from dataclasses import asdict, dataclass
from pathlib import Path
import hashlib
import json
import os

CODE_ROOT = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('Q3_WORKSPACE_ROOT', str(CODE_ROOT.parents[1]))).resolve()
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
    solver_threads: int = 1
    solver_backend: str = 'highs'
    formulation: str = 'v2_free'
    solver_focus: str = 'default'
    production_rescue: bool = False
    hard_06_seconds: float = 35.
    hard_other_seconds: float = 8.
    fd_delta: float = 100.
    fd_base: float = E_INITIAL
    fd_days: int = 28

    def __post_init__(self) -> None:
        if not isinstance(self.solver_threads, int) or self.solver_threads < 1:
            raise ValueError('求解线程数必须为正整数')
        if self.solver_backend not in ('auto','highs','gurobi') or self.formulation not in ('legacy','v2_free'):
            raise ValueError('求解后端或精确重构版本非法')
        if self.solver_focus not in ('default','bound'):
            raise ValueError('求解搜索重点非法')
        if self.hard_06_seconds<=0 or self.hard_other_seconds<=0:
            raise ValueError('节点硬时限必须为正数')
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
        payload = SOURCE.read_bytes()+json.dumps(asdict(self), sort_keys=True).encode('utf-8')
        for source in sorted(CODE_ROOT.glob('*.py')):
            if not source.name.startswith('test_'):
                payload += source.name.encode('utf-8')+source.read_bytes()
        return hashlib.sha256(payload).hexdigest()


def validate_production_rescue(config: Config) -> None:
    frozen=(config.production_rescue and config.scenarios==20 and config.tail==2 and not config.unconditional
        and config.terminal_scale==1. and config.interpolation=='linear' and config.feedback=='aggregate'
        and config.settlement=='final' and config.nodes==NODES and not config.deterministic and config.seconds==120.
        and config.gap==.03 and config.solver_threads==4 and config.solver_backend=='highs'
        and config.formulation=='legacy' and config.solver_focus=='default' and config.fd_delta==100.
        and config.fd_base==E_INITIAL and config.fd_days==28 and config.hard_06_seconds==35.
        and config.hard_other_seconds==8.)
    if not frozen:
        raise ValueError('production rescue冻结S20/tail2/四节点/24h模型/3%优先/HiGHS4线程/legacy fast/35与8秒')

def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+f'.{os.getpid()}.pending')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def write_csv(path: Path, frame: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+f'.{os.getpid()}.pending')
    with temporary.open('w', encoding='utf-8', newline='') as stream:
        frame.to_csv(stream, index=False, float_format='%.17g')
        stream.flush(); os.fsync(stream.fileno())
    temporary.replace(path)
    sync_directory(path.parent)


def sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
