(() => {
  const byId = (id) => document.getElementById(id);
  const form = byId("historyForm");
  const status = byId("historyStatus");
  const result = byId("historyResult");
  const historyButton = form.querySelector("button");
  const fundSearch = byId("fundSearch");
  const fundList = byId("fundList");
  const fundStatus = byId("fundStatus");
  const analyzeFund = byId("analyzeFund");
  const previousFundPage = byId("previousFundPage");
  const nextFundPage = byId("nextFundPage");
  const pageSize = 20;
  const fundPageSize = 10;
  let funds = [];
  let fundPage = 0;
  let catalogRequest = 0;
  let rows = [];
  let page = 0;

  async function readJson(url, signal) {
    const response = await fetch(url, { cache: "no-store", signal });
    const body = await response.json();
    if (!response.ok) throw new Error(body.message || "读取本地数据失败。");
    return body;
  }

  async function refreshCatalog() {
    const request = ++catalogRequest;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const { codes, funds: entries } = await readJson("/api/catalog?details=1", controller.signal);
      if (request !== catalogRequest) return;
      byId("localCodes").replaceChildren(...codes.map((code) => new Option(code)));
      byId("catalogStatus").textContent = `本地已有 ${codes.length} 只 ETF，输入代码可筛选。`;
      funds = entries;
      renderFunds();
    } catch {
      if (request !== catalogRequest) return;
      byId("catalogStatus").textContent = "暂时无法读取 ETF 列表，仍可输入代码查询历史。";
      fundStatus.textContent = "暂时无法读取本地基金清单，请刷新页面重试。";
    } finally {
      clearTimeout(timeout);
    }
  }

  function updateAnalyzeButton() {
    analyzeFund.disabled = historyButton.disabled || !fundList.querySelector(":checked");
  }

  function renderFunds() {
    const selected = fundList.querySelector(":checked")?.value;
    const query = fundSearch.value.trim().toLowerCase();
    const matches = funds.filter(({ code, name }) =>
      code.includes(query) || name.toLowerCase().includes(query));
    const pageCount = Math.ceil(matches.length / fundPageSize);
    fundPage = Math.min(fundPage, Math.max(0, pageCount - 1));
    const offset = fundPage * fundPageSize;
    const options = matches.slice(offset, offset + fundPageSize).map(({ code, name }) => {
      const label = document.createElement("label");
      label.className = "fund-option";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "catalogFund";
      radio.value = code;
      radio.checked = code === selected;
      const fundCode = document.createElement("strong");
      fundCode.textContent = code;
      label.append(radio, fundCode, name || "名称未收录");
      return label;
    });
    fundList.replaceChildren(...options);
    fundList.hidden = !matches.length;
    fundStatus.textContent = funds.length
      ? `匹配 ${matches.length} / ${funds.length} 只 ETF`
      : "暂无可分析的本地 ETF 记录。";
    byId("fundPageStatus").textContent = pageCount ? `第 ${fundPage + 1} / ${pageCount} 页` : "";
    previousFundPage.disabled = fundPage === 0;
    nextFundPage.disabled = fundPage + 1 >= pageCount;
    updateAnalyzeButton();
  }

  fundSearch.addEventListener("input", () => {
    fundPage = 0;
    renderFunds();
  });
  previousFundPage.addEventListener("click", () => { fundPage--; renderFunds(); });
  nextFundPage.addEventListener("click", () => { fundPage++; renderFunds(); });
  fundList.addEventListener("change", updateAnalyzeButton);
  analyzeFund.addEventListener("click", () => {
    const selected = fundList.querySelector(":checked");
    if (!selected || historyButton.disabled) return;
    byId("historyCode").value = selected.value;
    byId("historyHeading").focus({ preventScroll: true });
    byId("historyHeading").scrollIntoView({ block: "start" });
    form.requestSubmit();
  });

  function renderChart(records) {
    const chart = byId("shareChart");
    chart.replaceChildren();
    function append(tag, attrs, label) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, value));
      if (label !== undefined) node.textContent = label;
      chart.append(node);
    }
    const firstDate = Date.parse(records[0].stat_date);
    const lastDate = Date.parse(records[records.length - 1].stat_date);
    const values = records.map((row) => row.total_volume_shares / 10000);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = (max - min) * 0.08 || Math.max(max * 0.02, 0.0001);
    const lower = Math.max(0, min - padding);
    const upper = max + padding;
    const x = (row) => firstDate === lastDate ? 446 :
      108 + 676 * (Date.parse(row.stat_date) - firstDate) / (lastDate - firstDate);
    const y = (value) => 236 - 198 * (value - lower) / (upper - lower);
    append("text", { x: 108, y: 20 }, "总份额（万份）");
    for (let tick = 0; tick <= 4; tick++) {
      const value = lower + (upper - lower) * tick / 4;
      append("line", { x1: 108, x2: 784, y1: y(value), y2: y(value), stroke: "#d8dde8" });
      append("text", { x: 100, y: y(value) + 5, "text-anchor": "end" }, formatNumber(value));
    }
    if (records.length === 1) {
      append("circle", { cx: x(records[0]), cy: y(values[0]), r: 5, fill: "#1f4e79" });
      append("text", { x: 446, y: 263, "text-anchor": "middle" }, records[0].stat_date);
    } else {
      append("polyline", {
        points: records.map((row, i) => `${x(row)},${y(values[i])}`).join(" "),
        fill: "none", stroke: "#1f4e79", "stroke-width": 2.5,
      });
      append("text", { x: 108, y: 263 }, records[0].stat_date);
      append("text", { x: 784, y: 263, "text-anchor": "end" }, records[records.length - 1].stat_date);
    }
  }

  function changeText(shares) {
    if (shares === null) return "—";
    return (shares > 0 ? "+" : "") + formatNumber(shares / 10000);
  }

  function renderPage() {
    const tbody = byId("historyRows");
    tbody.replaceChildren();
    for (const record of rows.slice(page * pageSize, (page + 1) * pageSize)) {
      const row = tbody.insertRow();
      row.insertCell().textContent = record.stat_date;
      row.insertCell().textContent = formatNumber(record.total_volume_shares / 10000);
      const change = row.insertCell();
      change.textContent = changeText(record.change_shares);
      change.className = record.change_shares > 0 ? "increase" :
        record.change_shares < 0 ? "decrease" : "";
    }
    const total = Math.ceil(rows.length / pageSize);
    byId("pageStatus").textContent = `第 ${page + 1} / ${total} 页`;
    byId("previousPage").disabled = page === 0;
    byId("nextPage").disabled = page + 1 >= total;
  }

  byId("previousPage").addEventListener("click", () => { page--; renderPage(); });
  byId("nextPage").addEventListener("click", () => { page++; renderPage(); });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    historyButton.disabled = true;
    updateAnalyzeButton();
    status.textContent = "正在读取本地历史数据…";
    result.hidden = true;
    try {
      const params = new URLSearchParams(new FormData(form));
      const { data } = await readJson(`/api/history?${params}`);
      if (!data.length) {
        status.textContent = "所选区间暂无本地记录，可先在下方更新数据。";
        return;
      }
      const latest = data[data.length - 1];
      status.textContent = `${latest.code} ${latest.short_name || latest.name} · ${data[0].stat_date} 至 ${latest.stat_date}`;
      byId("latestShares").textContent = formatNumber(latest.total_volume_shares / 10000);
      byId("periodChange").textContent = changeText(latest.total_volume_shares - data[0].total_volume_shares);
      byId("historyCount").textContent = formatNumber(data.length);
      renderChart(data);
      rows = data.reverse();
      page = 0;
      renderPage();
      result.hidden = false;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      historyButton.disabled = false;
      updateAnalyzeButton();
    }
  });

  window.addEventListener("etf-data-updated", refreshCatalog);
  refreshCatalog();
})();
