"""3.3.4：用户确认的历史确定性继续价值有限差分标定。"""
from dataclasses import replace
import numpy as np
from .config import Config, DT, TOL
from .data import Inputs
from .scenarios import Scenarios
from .optimization import solve


class TerminalValues:
    def __init__(self, data: Inputs, config: Config):
        self.data, self.config = data, config
        self.cache: dict[tuple, dict] = {}

    def marginal(self, day: int, hour: int, delta: float) -> dict:
        key = (day, hour, delta)
        if key in self.cache:
            return self.cache[key]
        start = day*144+hour*6
        actual = self.data.actual.reshape(-1, 2)[start:start+144]
        if len(actual) != 144:
            raise ValueError('辅助继续价值问题需要完整历史24h')
        scenarios = Scenarios(actual[None, :, 0], actual[None, :, 1], np.ones(1), {})
        price = self.data.prices[(hour*6+np.arange(144))%144]
        # 辅助问题两侧必须同口径、同预算、零终端残值；以最优目标差而非真实回放成本差标定。
        config = replace(self.config, gap=0., feedback='aggregate')
        first = solve(scenarios, price, config.fd_base, config)
        second = solve(scenarios, price, config.fd_base+delta, config)
        value = (first.audit['objective']-second.audit['objective'])/delta
        if value <= 0:
            raise ValueError(f'历史边际价值非正({value})，不可捏造正值替换')
        row = {'history_day': day, 'hour': hour, 'complete_at_slot': start+144,
               'initial_soc': config.fd_base, 'delta': delta, 'value': value,
               'J_E': first.audit['objective'], 'J_E_plus_delta': second.audit['objective'],
               'seconds': first.audit['seconds']+second.audit['seconds']}
        self.cache[key] = row
        return row

    def value(self, day: int, endpoint_hour: int) -> tuple[float, dict]:
        hour = endpoint_hour%24
        # 模型要求仅当前日期以前完全实现；比当前节点截止更严格，不纳入当天实现样本。
        history = [j for j in range(day) if j*144+hour*6+144 <= day*144]
        history = history[-self.config.fd_days:]
        if not history:
            raise ValueError('没有完整历史辅助问题，不能人为指定终端价值')
        rows = [self.marginal(j, hour, self.config.fd_delta) for j in history]
        coefficient = float(np.median([row['value'] for row in rows]))
        return coefficient*self.config.terminal_scale, {
            'endpoint_hour': hour, 'history_days': history, 'median_unscaled': coefficient,
            'scale': self.config.terminal_scale, 'source_cutoff_slot': day*144,
            'delta': self.config.fd_delta, 'initial_soc': self.config.fd_base,
            'auxiliary_information': 'fully_realized_historical_24h_deterministic; terminal_value_only'}

    def stability(self, day: int, hour: int) -> list[dict]:
        """方案要求小范围扰动检查；50/100/200是delta=100的半倍/原值/双倍。"""
        return [self.marginal(day, hour, self.config.fd_delta*factor) for factor in (.5, 1., 2.)]
