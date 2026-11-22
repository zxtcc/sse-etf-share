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
  const favoriteList = byId("favoriteList");
  const favoriteStatus = byId("favoriteStatus");
  const toggleFavorite = byId("toggleFavorite");
  const favoriteKey = "sse-etf-favorites";
  const pageSize = 20;
  const fundPageSize = 10;
  let funds = [];
  let fundPage = 0;
  let catalogRequest = 0;
  let rows = [];
  let page = 0;
  let favorites = new Map();
  let favoritesReady = false;
  let savingFavorite = false;

  function legacyFavoriteCodes() {
    try {
      const saved = JSON.parse(localStorage.getItem(favoriteKey) || "[]");
      if (!Array.isArray(saved)) return [];
      return saved.filter(entry => Array.isArray(entry) &&
        typeof entry[0] === "string" && /^[0-9]{6}$/.test(entry[0])).map(entry => entry[0]);
    } catch {
      return [];
    }
  }

  async function loadFavorites() {
    favoriteStatus.hidden = false;
    favoriteStatus.textContent = "正在读取收藏…";
    try {
      const data = await readJson("/api/favorites");
      favorites = new Map(data.favorites);
    } catch {
      favoriteStatus.textContent = "无法读取项目收藏，请刷新页面重试。";
      return;
    }
    const legacy = legacyFavoriteCodes();
    try {
      for (const code of legacy) {
        if (!favorites.has(code)) {
          const data = await readJson(`/api/favorites/${code}`, undefined, "PUT");
          favorites = new Map(data.favorites);
        }
      }
      if (legacy.length) localStorage.removeItem(favoriteKey);
      favoriteStatus.hidden = true;
    } catch {
      favoriteStatus.textContent = "部分浏览器收藏未能迁移，原记录已保留。";
    }
    favoritesReady = true;
    renderFavorites();
    updateFundActions();
  }

  async function changeFavorite(code) {
    if (!favoritesReady || savingFavorite) return;
    const removing = favorites.has(code);
    savingFavorite = true;
    updateFundActions();
    favoriteStatus.hidden = false;
    try {
      const data = await readJson(`/api/favorites/${code}`, undefined, removing ? "DELETE" : "PUT");
      favorites = new Map(data.favorites);
      favoriteStatus.textContent = removing ? `已取消收藏 ${code}。` : `已收藏 ${code}。`;
      renderFavorites();
    } catch (error) {
      favoriteStatus.textContent = `无法保存收藏：${error.message}`;
    } finally {
      savingFavorite = false;
      updateFundActions();
    }
  }

  function renderFavorites() {
    const items = [...favorites].map(([code, savedName]) => {
      const name = funds.find(fund => fund.code === code)?.name || savedName || "名称未收录";
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${code} ${name}`;
      const analyze = document.createElement("button");
      analyze.type = "button";
      analyze.textContent = "数据分析";
      analyze.setAttribute("aria-label", `分析 ${code} ${name}`);
      analyze.addEventListener("click", () => openHistory(code));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-favorite";
      remove.textContent = "取消收藏";
      remove.setAttribute("aria-label", `取消收藏 ${code} ${name}`);
      remove.addEventListener("click", () => changeFavorite(code));
      item.append(label, analyze, remove);
      return item;
    });
    favoriteList.replaceChildren(...items);
    favoriteList.hidden = items.length === 0;
    byId("favoriteEmpty").hidden = !favoritesReady || items.length > 0;
  }

  async function readJson(url, signal, method = "GET") {
    const response = await fetch(url, { cache: "no-store", signal, method });
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
      renderFavorites();
    } catch {
      if (request !== catalogRequest) return;
      byId("catalogStatus").textContent = "暂时无法读取 ETF 列表，仍可输入代码查询历史。";
      fundStatus.textContent = "暂时无法读取本地基金清单，请刷新页面重试。";
    } finally {
      clearTimeout(timeout);
    }
  }

  function updateFundActions() {
    const selected = fundList.querySelector(":checked");
    analyzeFund.disabled = historyButton.disabled || !selected;
    toggleFavorite.disabled = !selected || !favoritesReady || savingFavorite;
    toggleFavorite.textContent = favorites.has(selected?.value) ? "取消收藏" : "收藏基金";
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
    updateFundActions();
  }

  fundSearch.addEventListener("input", () => {
    fundPage = 0;
    renderFunds();
  });
  previousFundPage.addEventListener("click", () => { fundPage--; renderFunds(); });
  nextFundPage.addEventListener("click", () => { fundPage++; renderFunds(); });
  fundList.addEventListener("change", updateFundActions);
  toggleFavorite.addEventListener("click", () => {
    const selected = fundList.querySelector(":checked");
    if (selected) changeFavorite(selected.value);
  });
  analyzeFund.addEventListener("click", () => {
    const selected = fundList.querySelector(":checked");
    if (selected) openHistory(selected.value);
  });

  function openHistory(code) {
    if (historyButton.disabled) return;
    byId("historyCode").value = code;
    byId("historyHeading").focus({ preventScroll: true });
    byId("historyHeading").scrollIntoView({ block: "start" });
    form.requestSubmit();
  }

  function renderChart(records) {
    const chart = byId("shareChart");
    const tooltip = byId("shareChartTooltip");
    tooltip.hidden = true;
    chart.replaceChildren();
    function append(tag, attrs, label) {
      const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
      Object.entries(attrs).forEach(([name, value]) => node.setAttribute(name, value));
      if (label !== undefined) node.textContent = label;
      chart.append(node);
      return node;
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
    const points = records.map((row, i) => ({
      date: row.stat_date, value: values[i], x: x(row), y: y(values[i]),
    }));
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
        points: points.map((point) => `${point.x},${point.y}`).join(" "),
        fill: "none", stroke: "#1f4e79", "stroke-width": 2.5,
      });
      append("text", { x: 108, y: 263 }, records[0].stat_date);
      append("text", { x: 784, y: 263, "text-anchor": "end" }, records[records.length - 1].stat_date);
    }

    const guide = append("line", { y1: 38, y2: 236, stroke: "#7590ad", "stroke-dasharray": "4 4", visibility: "hidden" });
    const marker = append("circle", { r: 5, fill: "#1f4e79", stroke: "#fff", "stroke-width": 2, visibility: "hidden" });
    const hitArea = append("rect", { x: 108, y: 38, width: 676, height: 198, fill: "transparent" });
    hitArea.addEventListener("pointermove", (event) => {
      const plot = hitArea.getBoundingClientRect();
      const cursorX = 108 + 676 * (event.clientX - plot.left) / plot.width;
      const point = points.reduce((nearest, candidate) =>
        Math.abs(candidate.x - cursorX) < Math.abs(nearest.x - cursorX) ? candidate : nearest);
      guide.setAttribute("x1", point.x);
      guide.setAttribute("x2", point.x);
      guide.setAttribute("visibility", "visible");
      marker.setAttribute("cx", point.x);
      marker.setAttribute("cy", point.y);
      marker.setAttribute("visibility", "visible");
      byId("shareChartTooltipDate").textContent = point.date;
      byId("shareChartTooltipValue").textContent = `总份额：${formatNumber(point.value)} 万份`;
      tooltip.hidden = false;
      const wrap = byId("shareChartWrap").getBoundingClientRect();
      const anchorX = plot.left - wrap.left + (point.x - 108) * plot.width / 676;
      const anchorY = plot.top - wrap.top + (point.y - 38) * plot.height / 198;
      const left = anchorX + 12 + tooltip.offsetWidth <= wrap.width
        ? anchorX + 12 : anchorX - tooltip.offsetWidth - 12;
      tooltip.style.left = `${Math.max(0, left)}px`;
      tooltip.style.top = `${Math.max(0, anchorY - tooltip.offsetHeight - 8)}px`;
    });
    const hideTooltip = () => {
      tooltip.hidden = true;
      guide.setAttribute("visibility", "hidden");
      marker.setAttribute("visibility", "hidden");
    };
    hitArea.addEventListener("pointerleave", hideTooltip);
    hitArea.addEventListener("pointercancel", hideTooltip);
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
    updateFundActions();
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
      updateFundActions();
    }
  });

  window.addEventListener("etf-data-updated", refreshCatalog);
  loadFavorites();
  refreshCatalog();
})();
