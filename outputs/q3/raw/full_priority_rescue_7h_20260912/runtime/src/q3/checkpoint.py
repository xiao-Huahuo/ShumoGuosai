"""单写入者锁、输入摘要、带校验的节点求解快照。"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Iterator
import numpy as np
from .config import Config, write_json
from .physics import Policy


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+', encoding='utf-8') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f'已有进程占用{path}，禁止重复运行') from error
        stream.seek(0); stream.truncate(); stream.write(str(os.getpid())); stream.flush(); os.fsync(stream.fileno())
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def request_digest(config: Config, *values: object) -> str:
    digest = hashlib.sha256(config.signature().encode('utf-8'))
    for value in values:
        if value is None:
            digest.update(b'None'); continue
        array = np.asarray(value, dtype='<f8')
        digest.update(str(array.shape).encode('utf-8')); digest.update(array.tobytes())
    return digest.hexdigest()


def save_snapshot(path: Path, signature: str, policy: Policy, audit: dict) -> None:
    content = {'signature': signature, 'policy': {k: getattr(policy, k).tolist() for k in ('grid', 'charge_cap', 'discharge_cap')},
               'audit': audit}
    payload = json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    write_json(path, {'sha256': hashlib.sha256(payload).hexdigest(), 'content': content})


def load_snapshot(path: Path, signature: str) -> tuple[Policy, dict] | None:
    if not path.exists():
        return None
    wrapper = json.loads(path.read_text(encoding='utf-8')); content = wrapper['content']
    payload = json.dumps(content, sort_keys=True, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if hashlib.sha256(payload).hexdigest() != wrapper['sha256'] or content['signature'] != signature:
        raise ValueError('节点快照损坏或输入/配置/代码不同，拒绝复用策略和下界')
    return Policy(*(np.asarray(content['policy'][k], dtype=float) for k in ('grid', 'charge_cap', 'discharge_cap'))), content['audit']
