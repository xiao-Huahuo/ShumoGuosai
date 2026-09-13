"""7.2/7.4：附件4校验、Q2/Q3预测复用与同日联合OOS残差。"""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from src.q3.data import Inputs as Q3Inputs, read_inputs as read_q3_inputs
from .config import ATTACHMENTS, DT, Q2_RUN, ROOT, write_csv, write_json
from . import price as price_module
from .price import Forecasts, rolling_forecasts


def _endpoint_minutes(value: object) -> int:
    if isinstance(value, str) and value == "0:00+1":
        return 1440
    if hasattr(value, "hour") and hasattr(value, "minute"):
        result = int(value.hour) * 60 + int(value.minute)
        return 1440 if result == 0 else result
    raise ValueError(f"无法识别附件4时刻：{value!r}")


def read_prices(path: Path) -> np.ndarray:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        rows = list(sheet.values)
    finally:
        workbook.close()
    if len(rows) != 366 or len(rows[0]) != 145:
        raise ValueError("附件4必须为表头加365日、每日144时段")
    if [_endpoint_minutes(value) for value in rows[0][1:]] != list(range(10, 1441, 10)):
        raise ValueError("附件4右端点时刻错位")
    dates = [pd.Timestamp(row[0]).normalize() for row in rows[1:]]
    expected = list(pd.date_range("2025-01-01", periods=365, freq="D"))
    if dates != expected:
        raise ValueError("附件4日期不连续或不属于2025年")
    values = np.asarray([row[1:] for row in rows[1:]], dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("附件4电价存在缺失、非有限值或非正值")
    return values


@dataclass
class Inputs:
    q3: Q3Inputs
    actual_prices: np.ndarray
    price: Forecasts
    provenance: dict

    def point_net(self, day: int, hour: int, length: int) -> np.ndarray:
        name = self.q3.selected[day]
        load = self.q3.load(day, name)[hour * 6:hour * 6 + length]
        if length == 144:
            pv = self.q3.pv(day, hour)
        elif length == 288 and hour == 0:
            if day < 7:
                raise ValueError("48h递推光伏至少需要7日历史")
            pv = np.r_[self.q3.pv(day, 0), self.q3.actual[day - 6, :, 1]]
        else:
            raise ValueError("仅支持四节点24h或0:00的48h预测")
        if len(load) != length or len(pv) != length or not np.isfinite(load).all():
            raise ValueError("因果负荷/光伏预测支持不足")
        return (load - pv) * DT

    def point_price(self, day: int, hour: int, length: int) -> np.ndarray:
        result = self.price.values[day, hour * 6:hour * 6 + length]
        if len(result) != length or not np.isfinite(result).all():
            raise ValueError("严格因果价格预测支持不足")
        return result.copy()

    def _net_history(self, day: int, hour: int, length: int) -> tuple[np.ndarray, np.ndarray]:
        name = self.q3.selected[day]
        if length == 144:
            days, load_error, pv_error, _ = self.q3.history(
                day, hour, name, forecast_hour=hour, length=length
            )
            return days, (load_error - pv_error) * DT
        if length != 288 or hour != 0:
            raise ValueError("历史残差支持与当前预测窗口不一致")
        cutoff = day * 144
        actual = self.q3.actual.reshape(-1, 2)
        ids, errors = [], []
        for history_day in range(7, day):
            start = history_day * 144
            if start + length > cutoff:
                continue
            load = self.q3.load_store[name][history_day, :2].reshape(-1)
            pv = np.r_[self.q3.pv(history_day, 0), self.q3.actual[history_day - 6, :, 1]]
            if len(load) != length or not np.isfinite(load).all():
                continue
            realized = (actual[start:start + length, 0] - actual[start:start + length, 1]) * DT
            ids.append(history_day)
            errors.append(realized - (load - pv) * DT)
        return np.asarray(ids, dtype=int), np.asarray(errors, dtype=float).reshape(-1, length)

    def joint_history(self, day: int, hour: int, length: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        days, net_errors = self._net_history(day, hour, length)
        price_flat = self.price.residuals.reshape(-1)
        selected_days, selected_net, selected_price = [], [], []
        for history_day, net_error in zip(days, net_errors):
            start = int(history_day) * 144 + hour * 6
            price_error = price_flat[start:start + length]
            if len(price_error) == length and np.isfinite(price_error).all():
                selected_days.append(int(history_day))
                selected_net.append(net_error)
                selected_price.append(price_error)
        return (
            np.asarray(selected_days, dtype=int),
            np.asarray(selected_net, dtype=float).reshape(-1, length),
            np.asarray(selected_price, dtype=float).reshape(-1, length),
        )

    def prefix(self, day: int, hour: int) -> np.ndarray:
        if hour == 0:
            return np.empty(0)
        end = hour * 6
        actual_net = (self.q3.actual[day, :end, 0] - self.q3.actual[day, :end, 1]) * DT
        net_error = actual_net - self.point_net(day, 0, 144)[:end]
        price_error = self.actual_prices[day, :end] - self.price.values[day, :end]
        one = min(6, end)
        three = min(18, end)
        return np.asarray([
            price_error.mean(),
            net_error.mean(),
            price_error[-one:].mean(),
            net_error[-one:].mean(),
            price_error[-three:].mean(),
            net_error[-three:].mean(),
            net_error.sum(),
        ])


def read_inputs(processed: Path | None = None, q2_run: Path = Q2_RUN) -> Inputs:
    q3 = read_q3_inputs(q2_run)
    attachment = ATTACHMENTS / "附件4.xlsx"
    actual_prices = read_prices(attachment)
    folder = processed or ROOT / "inputs/q4/processed"
    attachment_hash = hashlib.sha256(attachment.read_bytes()).hexdigest()
    price_code_hash = hashlib.sha256(Path(price_module.__file__).read_bytes()).hexdigest()
    manifest_path = folder / "source_manifest.json"
    cached = None
    if manifest_path.exists() and (folder / "price_forecasts.csv").exists() and (folder / "price_residuals.csv").exists():
        manifest = __import__("json").loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("attachment4_sha256") == attachment_hash
                and manifest.get("price_code_sha256") == price_code_hash):
            values = pd.read_csv(folder / "price_forecasts.csv", float_precision="round_trip").to_numpy(float)
            residuals = pd.read_csv(folder / "price_residuals.csv", float_precision="round_trip").to_numpy(float)
            if values.shape == (365, 288) and residuals.shape == (365, 144):
                cached = Forecasts(values, residuals, manifest["price_model"])
    forecasts = cached or rolling_forecasts(actual_prices)
    provenance = {
        "q2_run": str(q2_run.resolve()),
        "attachment4": str(attachment.resolve()),
        "attachment4_sha256": attachment_hash,
        "price_code_sha256": price_code_hash,
        "price_model": forecasts.audit,
        "net_forecast": "Q2 selected rolling-OOS load + attachment3 forecast-origin PV",
        "q4_2_second_day_pv": "target-day minus 7 days actual PV, available at current 0:00",
        "information_boundary": "future actual load/PV/price used only by replay and residuals after realization",
    }
    if processed is not None and cached is None:
        processed.mkdir(parents=True, exist_ok=True)
        write_csv(processed / "actual_prices.csv", pd.DataFrame(actual_prices))
        write_csv(processed / "price_forecasts.csv", pd.DataFrame(
            forecasts.values.reshape(365, 288)
        ))
        write_csv(processed / "price_residuals.csv", pd.DataFrame(forecasts.residuals))
        write_json(processed / "source_manifest.json", provenance)
    return Inputs(q3, actual_prices, forecasts, provenance)
