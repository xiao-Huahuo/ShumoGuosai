"""3.3.4：用户确认的历史确定性继续价值有限差分标定。"""
from dataclasses import replace
from concurrent.futures import Executor
import json
import hashlib
from pathlib import Path
import numpy as np
from .config import Config, TOL, write_json
from .data import Inputs
from .scenarios import Scenarios
from .optimization import solve


class TerminalValues:
    def __init__(self, data: Inputs, config: Config, executor: Executor | None = None, cache_path: Path | None = None):
        self.data, self.config, self.executor = data, config, executor
        self.cache_path = cache_path
        self.cache_signature = hashlib.sha256((config.signature()+json.dumps(data.provenance, sort_keys=True)).encode('utf-8')).hexdigest()
        self.cache: dict[tuple, dict] = {}
        if cache_path and cache_path.exists():
            stored = json.loads(cache_path.read_text(encoding='utf-8'))
            content = stored['content']
            payload = json.dumps(content, sort_keys=True, allow_nan=False).encode('utf-8')
            if stored['sha256'] != hashlib.sha256(payload).hexdigest() or content['signature'] != self.cache_signature:
                raise ValueError('FD持久缓存与当前配置/源码不一致')
            for row in content['rows']:
                self.cache[(int(row['history_day']), int(row['hour']), float(row['delta']))] = row

    def remember(self, row: dict) -> None:
        self.cache[(row['history_day'], row['hour'], row['delta'])] = row
        if self.cache_path:
            content = {'signature': self.cache_signature, 'rows': list(self.cache.values())}
            payload = json.dumps(content, sort_keys=True, allow_nan=False).encode('utf-8')
            write_json(self.cache_path, {'sha256': hashlib.sha256(payload).hexdigest(), 'content': content})

    def request(self, day: int, hour: int, delta: float) -> tuple:
        start = day*144+hour*6
        return (day, hour, delta, self.data.actual.reshape(-1, 2)[start:start+144].copy(),
                self.data.prices[(hour*6+np.arange(144))%144].copy(), self.config)

    def marginal(self, day: int, hour: int, delta: float) -> dict:
        key = (day, hour, delta)
        if key in self.cache:
            return self.cache[key]
        row = marginal_job(self.request(day, hour, delta))
        self.remember(row)
        return row

    def value(self, day: int, endpoint_hour: int) -> tuple[float, dict]:
        hour = endpoint_hour%24
        # 模型要求仅当前日期以前完全实现；比当前节点截止更严格，不纳入当天实现样本。
        history = [j for j in range(day) if j*144+hour*6+144 <= day*144]
        history = history[-self.config.fd_days:]
        if not history:
            raise ValueError('没有完整历史辅助问题，不能人为指定终端价值')
        missing = [j for j in history if (j, hour, self.config.fd_delta) not in self.cache]
        if self.executor is not None and len(missing) > 1:
            requests = [self.request(j, hour, self.config.fd_delta) for j in missing]
            for row in self.executor.map(marginal_job, requests):
                self.remember(row)
        rows = [self.marginal(j, hour, self.config.fd_delta) for j in history]
        coefficient = float(np.median([row['value'] for row in rows]))
        if coefficient <= 0:
            raise ValueError(f'历史中位数为零(day={day}, hour={hour})，与v4严格正终端价值冲突，需确认，禁止填任意正数')
        return coefficient*self.config.terminal_scale, {
            'endpoint_hour': hour, 'history_days': history, 'median_unscaled': coefficient,
            'scale': self.config.terminal_scale, 'source_cutoff_slot': day*144,
            'delta': self.config.fd_delta, 'initial_soc': self.config.fd_base,
            'auxiliary_information': 'fully_realized_historical_24h_deterministic; terminal_value_only'}

    def stability(self, day: int, hour: int) -> list[dict]:
        """方案要求小范围扰动检查；50/100/200是delta=100的半倍/原值/双倍。"""
        return [self.marginal(day, hour, self.config.fd_delta*factor) for factor in (.5, 1., 2.)]


def marginal_job(request: tuple) -> dict:
    day, hour, delta, actual, price, config = request
    start = day*144+hour*6
    if len(actual) != 144:
        raise ValueError('辅助继续价值问题需要完整历史24h')
    scenarios = Scenarios(actual[None, :, 0], actual[None, :, 1], np.ones(1), {})
    # 辅助问题两侧必须同口径、同预算、零终端残值；以最优目标差而非真实回放成本差标定。
    config = replace(config,gap=0.,feedback='aggregate',solver_threads=1,production_rescue=False)
    first = solve(scenarios, price, config.fd_base, config)
    second = solve(scenarios, price, config.fd_base+delta, config)
    value = (first.audit['objective']-second.audit['objective'])/delta
    if value < -TOL:
        raise ValueError(f'历史边际价值为负({value})，需检查辅助问题证书')
    value = max(0., value)  # 仅消除浮点舍入负零；单个历史日零价值是合法的。
    row = {'history_day': day, 'hour': hour, 'complete_at_slot': start+144,
           'initial_soc': config.fd_base, 'delta': delta, 'value': value,
           'J_E': first.audit['objective'], 'J_E_plus_delta': second.audit['objective'],
           'seconds': first.audit['seconds']+second.audit['seconds']}
    return row
