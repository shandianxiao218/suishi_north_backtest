"""测试 report.py 研究报告生成。"""
from __future__ import annotations

from pathlib import Path

import pytest
from suishi_north_backtest.report import generate_report


class TestReportContent:
    """测试报告内容完整性。"""

    def test_report_contains_data_version(self, tmp_path: Path) -> None:
        """报告必须包含数据版本。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "数据版本" in content
        assert "deterministic-fixture-v1-2026-05-18" in content

    def test_report_contains_parameter_set(self, tmp_path: Path) -> None:
        """报告必须包含参数集信息。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "参数集" in content
        assert "ADR-0002-defaults-fixture-run" in content

    def test_report_contains_sample_windows(self, tmp_path: Path) -> None:
        """报告必须包含样本区间信息。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "样本区间" in content
        assert "样本内" in content or "sample_in" in content
        assert "样本外" in content or "sample_out" in content
        assert "近期窗口" in content or "recent" in content

    def test_report_contains_research_limitation(self, tmp_path: Path) -> None:
        """报告必须包含研究限制说明。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "研究限制" in content

    def test_report_does_not_contain_investment_advice(self, tmp_path: Path) -> None:
        """报告不得包含投资建议措辞。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        # 禁止出现的投资建议措辞
        forbidden_phrases = [
            "建议买入",
            "建议卖出",
            "推荐投资",
            "应该买入",
            "应该卖出",
            "建议投资",
        ]
        for phrase in forbidden_phrases:
            assert phrase not in content


class TestReportStructure:
    """测试报告结构完整性。"""

    def test_report_contains_required_sections(self, tmp_path: Path) -> None:
        """报告必须包含必需章节。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        # 必需的章节标题
        required_sections = [
            "数据版本",
            "参数集",
            "股票池",
            "样本区间",
            "策略摘要",
            "双轨对比",
            "基准对比",
            "参数敏感性",
            "最大回撤",
            "交易样本",
            "风险提示",
            "研究限制",
        ]
        for section in required_sections:
            assert section in content

    def test_report_contains_disclaimer(self, tmp_path: Path) -> None:
        """报告必须包含免责声明。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "这是研究输出，不是投资建议。" in content

    def test_report_contains_track_comparison(self, tmp_path: Path) -> None:
        """报告必须包含双轨对比数据。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "pure_structure" in content or "纯结构" in content
        assert "mainline_filtered" in content or "主线过滤" in content

    def test_report_contains_benchmark_comparison(self, tmp_path: Path) -> None:
        """报告必须包含基准对比数据。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        # 至少包含一个基准
        has_benchmark = any(
            benchmark in content
            for benchmark in ["CSI300", "CSI500", "CSI1000", "沪深300", "中证500", "中证1000"]
        )
        assert has_benchmark

    def test_report_contains_max_drawdown(self, tmp_path: Path) -> None:
        """报告必须包含最大回撤信息。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "最大回撤" in content

    def test_report_contains_sensitivity(self, tmp_path: Path) -> None:
        """报告必须包含参数敏感性信息。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "参数敏感性" in content


class TestReportGeneration:
    """测试报告生成功能。"""

    def test_generate_report_creates_file(self, tmp_path: Path) -> None:
        """测试 generate_report 创建报告文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()
        assert report_path.is_file()

    def test_generate_report_overwrites_existing(self, tmp_path: Path) -> None:
        """测试 generate_report 覆盖已有文件。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        report_path = output_dir / "report.md"
        report_path.write_text("old content", encoding="utf-8")

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        content = report_path.read_text(encoding="utf-8")
        assert content != "old content"
        assert "数据版本" in content

    def test_generate_report_is_markdown(self, tmp_path: Path) -> None:
        """测试生成的报告是 Markdown 格式。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.suffix == ".md"

        content = report_path.read_text(encoding="utf-8")
        # Markdown 标题特征
        assert "#" in content or content.strip().startswith("#")

    def test_generate_report_contains_trade_sample(self, tmp_path: Path) -> None:
        """报告必须包含交易样本信息。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "交易样本" in content
        # 应该有交易次数信息
        assert "交易次数" in content or "trade_count" in content or "笔交易" in content

    def test_generate_report_contains_risk_warning(self, tmp_path: Path) -> None:
        """报告必须包含风险提示。"""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        from suishi_north_backtest.data import FixtureDataProvider
        from suishi_north_backtest.config import BacktestConfig

        provider = FixtureDataProvider()
        config = BacktestConfig(
            name="test-report",
            start_date="2024-01-01",
            end_date="2024-12-31",
            initial_cash=1_000_000,
            output_dir=output_dir,
            data_source="fixture",
        )
        data_set = provider.load(config)

        generate_report(config, data_set)

        report_path = output_dir / "report.md"
        assert report_path.exists()

        content = report_path.read_text(encoding="utf-8")
        assert "风险提示" in content