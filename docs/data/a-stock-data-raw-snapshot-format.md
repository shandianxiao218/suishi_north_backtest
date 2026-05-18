# a-stock-data 原始快照输入规范

## 目的

定义外部 `a-stock-data` 原始行情数据在本仓库中的本地落盘格式。

策略逻辑不直接依赖原始字段形状。所有原始数据必须通过 `raw_data.py` 校验后，再由 `market_data.py` 标准化为内部字段。

## 目录结构

```text
data/a_stock_data_raw/<snapshot-name>/
  manifest.json
  stock_daily.csv
  index_daily.csv
  industry_map.csv
  industry_daily_amount.csv
  trading_calendar.csv
```

## manifest.json

必需字段：

```json
{
  "data_version": "a-stock-data-raw-2026-05-18",
  "source": "a-stock-data",
  "created_at": "2026-05-18T00:00:00+08:00",
  "stock_daily_file": "stock_daily.csv",
  "index_daily_file": "index_daily.csv",
  "industry_map_file": "industry_map.csv",
  "industry_daily_amount_file": "industry_daily_amount.csv",
  "trading_calendar_file": "trading_calendar.csv"
}
```

`data_version` 为必需字段，不能为空。

文件名映射字段（`stock_daily_file` 等）允许自定义文件名，但文件必须存在于快照目录内。

## stock_daily.csv

股票日线行情。

必需列：

```text
trade_date,symbol,open,high,low,close,volume,amount
```

要求：

- `trade_date` 格式 `YYYY-MM-DD`。
- `symbol` 为股票代码，如 `000001`。
- 数值字段可为空（停牌等情况），空值在标准化层处理。
- 编码 `utf-8-sig` 或兼容 UTF-8。

## index_daily.csv

指数日线行情。

必需列：

```text
trade_date,index_code,open,high,low,close,volume,amount
```

要求：

- `index_code` 为指数代码，如 `000300`（沪深300）、`000905`（中证500）、`000852`（中证1000）。

## industry_map.csv

股票到二级行业映射。

必需列：

```text
symbol,industry_level2
```

要求：

- `industry_level2` 为中文行业名。
- 一只股票可对应一个二级行业。

## industry_daily_amount.csv

二级行业每日成交金额。

必需列：

```text
trade_date,industry_level2,amount
```

要求：

- `industry_level2` 与 `industry_map.csv` 中的行业名一致。
- `amount` 为成交金额，数值类型。

## trading_calendar.csv

交易日历。

必需列：

```text
trade_date,is_open
```

要求：

- `is_open` 为 `1`（开市）或 `0`（休市）。

## 校验规则

`raw_data.py` 模块负责校验以下内容：

1. 快照目录必须存在。
2. `manifest.json` 必须存在且为合法 JSON。
3. `manifest.json` 必须包含 `data_version` 字段且不为空。
4. manifest 中列出的所有文件必须存在于快照目录内。
5. 每个 CSV 文件必须包含规定的必需列。
6. CSV 应使用 `utf-8-sig` 或兼容 UTF-8 编码，确保中文正常读取。
