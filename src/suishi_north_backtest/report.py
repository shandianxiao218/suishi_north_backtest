"""MVP-1 研究报告生成模块。

将回测结果汇总为 Markdown 研究报告 report.md。

报告内容基于 Mvp1DataSet 的全部字段，不依赖策略引擎内部模块。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suishi_north_backtest.config import BacktestConfig
    from suishi_north_backtest.data import Mvp1DataSet


_DISCLAIMER = "这是研究输出，不是投资建议。"


def generate_report(config: BacktestConfig, data_set: Mvp1DataSet) -> None:
    """生成 MVP-1 研究报告，写入 config.output_dir / report.md。"""
    sections = [
        _build_header(config, data_set),
        _build_data_version(data_set),
        _build_parameter_set(data_set),
        _build_universe(data_set),
        _build_sample_windows(data_set),
        _build_strategy_summary(data_set),
        _build_track_comparison(data_set),
        _build_benchmark_comparison(data_set),
        _build_sensitivity(data_set),
        _build_max_drawdown(data_set),
        _build_trade_sample(data_set),
        _build_risk_warning(),
        _build_research_limitation(),
    ]
    content = "\n\n".join(sections) + "\n"
    report_path: Path = config.output_dir / "report.md"
    report_path.write_text(content, encoding="utf-8")


def _build_header(config: BacktestConfig, data_set: Mvp1DataSet) -> str:
    return (
        f"# MVP-1 研究报告：{config.name}\n\n"
        f"- 回测区间：{config.start_date} 至 {config.end_date}\n"
        f"- 初始资金：{config.initial_cash:,}\n"
        f"- 数据源：{config.data_source}"
    )


def _build_data_version(data_set: Mvp1DataSet) -> str:
    return f"## 数据版本\n\n{data_set.data_version}"


def _build_parameter_set(data_set: Mvp1DataSet) -> str:
    return f"## 参数集\n\n{data_set.parameter_set}"


def _build_universe(data_set: Mvp1DataSet) -> str:
    return f"## 股票池\n\n{data_set.universe}"


def _build_sample_windows(data_set: Mvp1DataSet) -> str:
    metrics = data_set.metrics
    windows = metrics.get("sample_windows", {})
    lines = ["## 样本区间", ""]
    if not windows:
        lines.append("无样本区间数据。")
        return "\n".join(lines)

    label_map = {
        "sample_in": "样本内",
        "sample_out": "样本外",
        "recent": "近期窗口",
    }
    for key, label in label_map.items():
        val = windows.get(key)
        if val is not None:
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                lines.append(f"- {label}：{val[0]} 至 {val[1]}")
            else:
                lines.append(f"- {label}：{val}")

    return "\n".join(lines)


def _build_strategy_summary(data_set: Mvp1DataSet) -> str:
    m = data_set.metrics
    total_ret = _fmt_pct(m.get("total_return"))
    max_dd = _fmt_pct(m.get("max_drawdown"))
    pf = _fmt_num(m.get("profit_factor"))
    wr = _fmt_pct(m.get("win_rate"))
    tc = m.get("trade_count", "N/A")

    return (
        "## 策略摘要\n\n"
        "| 指标 | 值 |\n"
        "|------|----|\n"
        f"| 总收益率 | {total_ret} |\n"
        f"| 最大回撤 | {max_dd} |\n"
        f"| 盈亏比 (Profit Factor) | {pf} |\n"
        f"| 胜率 | {wr} |\n"
        f"| 交易次数 | {tc} |"
    )


def _build_track_comparison(data_set: Mvp1DataSet) -> str:
    rows = data_set.track_comparison
    if not rows:
        return "## 双轨对比\n\n无双轨对比数据。"

    lines = [
        "## 双轨对比",
        "",
        "| 指标 | 纯结构 (pure_structure) | 主线过滤 (mainline_filtered) | 差异 |",
        "|------|------------------------|-----------------------------|------|",
    ]
    for row in rows:
        metric = row.get("metric", "")
        ps = row.get("pure_structure_track", "")
        mf = row.get("mainline_filtered_track", "")
        delta = row.get("delta", "")
        lines.append(f"| {metric} | {ps} | {mf} | {delta} |")

    return "\n".join(lines)


def _build_benchmark_comparison(data_set: Mvp1DataSet) -> str:
    rows = data_set.benchmark_comparison
    if not rows:
        return "## 基准对比\n\n无基准对比数据。"

    # 收集所有基准代码
    benchmarks_seen: list[str] = []
    for row in rows:
        bm = str(row.get("benchmark", ""))
        if bm and bm not in benchmarks_seen:
            benchmarks_seen.append(bm)

    lines = [
        "## 基准对比",
        "",
        "| 区间 | 基准 | 策略收益率 | 基准收益率 | 超额收益 |",
        "|------|------|-----------|-----------|---------|",
    ]
    for row in rows:
        period = row.get("period", "")
        bm = row.get("benchmark", "")
        strat_ret = row.get("strategy_return", "")
        bm_ret = row.get("benchmark_return", "")
        excess = row.get("excess_return", "")
        lines.append(
            f"| {period} | {bm} | {strat_ret}% | {bm_ret}% | {excess}% |"
        )

    return "\n".join(lines)


def _build_sensitivity(data_set: Mvp1DataSet) -> str:
    rows = data_set.sensitivity
    if not rows:
        return "## 参数敏感性\n\n无参数敏感性数据。"

    lines = [
        "## 参数敏感性",
        "",
        "| 参数 | 基线值 | 变体值 | 样本内 | 样本外 | 过拟合风险 | 接受 |",
        "|------|--------|--------|--------|--------|-----------|------|",
    ]
    for row in rows:
        param = row.get("parameter", "")
        bv = row.get("baseline_value", "")
        vv = row.get("variant_value", "")
        si = row.get("sample_in_metric", "")
        so = row.get("sample_out_metric", "")
        risk = row.get("overfit_risk", "")
        accepted = row.get("accepted", "")
        lines.append(
            f"| {param} | {bv} | {vv} | {si} | {so} | {risk} | {accepted} |"
        )

    return "\n".join(lines)


def _build_max_drawdown(data_set: Mvp1DataSet) -> str:
    m = data_set.metrics
    max_dd = _fmt_pct(m.get("max_drawdown"))
    tracks = m.get("tracks", {})
    track_lines = ""
    if isinstance(tracks, dict):
        for track_name, track_data in tracks.items():
            if isinstance(track_data, dict) and "max_drawdown" in track_data:
                track_dd = _fmt_pct(track_data["max_drawdown"])
                track_lines += f"\n- {track_name}: {track_dd}"

    body = f"## 最大回撤\n\n整体最大回撤：{max_dd}"
    if track_lines:
        body += f"\n\n分轨道：{track_lines}"
    return body


def _build_trade_sample(data_set: Mvp1DataSet) -> str:
    trades = data_set.trades
    m = data_set.metrics
    tc = m.get("trade_count", len(trades))

    lines = [f"## 交易样本", "", f"共 {tc} 笔交易。"]

    if not trades:
        lines.append("无交易记录。")
        return "\n".join(lines)

    # 取前 5 笔
    sample = trades[:5]
    lines.append("")
    lines.append(
        "| 交易ID | 轨道 | 标的 | 信号日 | 买入日 | 买入价 | "
        "卖出日 | 卖出价 | 退出原因 | 净盈亏 |"
    )
    lines.append(
        "|--------|------|------|--------|--------|--------|"
        "--------|--------|----------|--------|"
    )
    for t in sample:
        lines.append(
            f"| {t.get('trade_id', '')} "
            f"| {t.get('track', '')} "
            f"| {t.get('symbol', '')} "
            f"| {t.get('entry_signal_date', '')} "
            f"| {t.get('entry_date', '')} "
            f"| {t.get('entry_price', '')} "
            f"| {t.get('exit_date', '')} "
            f"| {t.get('exit_price', '')} "
            f"| {t.get('exit_reason', '')} "
            f"| {t.get('net_pnl', '')} |"
        )

    if len(trades) > 5:
        lines.append(f"\n... 及其他 {len(trades) - 5} 笔交易。")

    return "\n".join(lines)


def _build_risk_warning() -> str:
    return (
        "## 风险提示\n\n"
        "- 历史回测表现不代表未来收益。\n"
        "- 策略参数基于样本内数据设定，可能存在过拟合风险。\n"
        "- MVP-1 使用日线代理规则，未包含盘中执行细节。\n"
        "- 实际交易中的滑点、流动性、停牌等因素可能导致结果偏离回测。\n"
        "- 本报告不构成任何投资建议。"
    )


def _build_research_limitation() -> str:
    return (
        "## 研究限制\n\n"
        f"- {_DISCLAIMER}\n"
        "- MVP-1 是日线代理研究系统，不等同于完整实盘交易系统。\n"
        "- 主线使用机械化代理（二级行业成交金额排名），非主观判断。\n"
        "- C 点识别使用日线规则近似执行周期转向。\n"
        "- 样本外区间有限，稳健性结论需更多数据验证。\n"
        "- 存在幸存者偏差：回测基于当前存续股票，未包含已退市股票。"
    )


def _fmt_pct(value: object) -> str:
    """将浮点小数格式化为百分比字符串。"""
    if value is None:
        return "N/A"
    try:
        return f"{float(value) * 100:.2f}%"
    except (ValueError, TypeError):
        return str(value)


def _fmt_num(value: object) -> str:
    """将数值格式化为可读字符串。"""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.2f}"
    except (ValueError, TypeError):
        return str(value)
