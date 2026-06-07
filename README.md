# 上交所 ETF 份额查询 Web 程序

这是一个使用 Python + Flask 实现的小型 Web 程序。页面包含“单日份额查询”和“数据汇总”两个板块，可查询指定 ETF 的单日份额，也可按日期区间批量更新上海证券交易所 ETF 规模数据。

## 依赖项

- Python 3.9 或更高版本
- Flask
- requests
- openpyxl

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

## 启动程序

```bash
python3 app.py
```

启动后访问：

```text
http://127.0.0.1:5000
```

## 停止程序

在运行程序的终端按 `Ctrl+C` 即可停止。

## 使用方式

### 单日份额查询

1. 打开页面。
2. 在“单日份额查询”板块输入 6 位 ETF 代码，例如 `510050`。
3. 选择查询日期，例如 `2025-09-04`。
4. 点击“查询”，页面展示基金代码、日期和总份额（万份）。
5. 如果本地 `data/ETF代码.xlsx` 已有该日期记录，程序直接读取本地数据；如果没有，再访问上交所并写入本地 Excel。

### 数据汇总

1. 在“数据汇总”板块选择起始日期和终止日期。
2. 起始日期默认 `2023-01-01`，终止日期默认最近一个非周末日期。
3. 点击“数据更新”，程序按日期分页请求上交所 ETF 数据，并保存到 `data/ETF代码.xlsx`。
4. 如果某个日期已在 `data/_update_status.json` 标记为全量更新，程序会跳过该日期，减少访问频率。

## 数据文件

- 每只 ETF 一个 Excel 文件，命名为 `data/ETF代码.xlsx`。
- Excel 字段包括日期、ETF 代码、基金名称、基金简称、ETF 类型、总份额（万份）、总份额（份）、更新时间。
- `data/_update_status.json` 用于记录已完成全量更新的日期。

## 数据来源

- 页面来源：https://www.sse.com.cn/market/funddata/volumn/etfvolumn/
- 数据接口：`https://query.sse.com.cn/commonQuery.do`
- 关键参数：`sqlId=COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L`，`STAT_DATE=YYYY-MM-DD`

说明：上海证券交易所页面披露的份额单位为“万份”。单日查询页面仅展示“万份”，Excel 文件中同时保存“万份”和换算后的“份”。
