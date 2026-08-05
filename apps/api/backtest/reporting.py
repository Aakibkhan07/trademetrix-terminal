"""Phase E: professional reporting — shareable read-only HTML report + HMAC token.

The interactive report is a single self-contained HTML document (no external
assets, inline CSS/JS) embedding a copy of the exact GET /{run_id} payload.
Access is gated by an HMAC-SHA256 token minted per run id, so the page can be
shared read-only without authentication.
"""
from __future__ import annotations

import hashlib
import hmac
import json

from core.config import settings

_TOKEN_BYTES = 24


def share_token(run_id: str) -> str:
    return hmac.new(settings.secret_key.encode(), run_id.encode(), hashlib.sha256).hexdigest()[:_TOKEN_BYTES]


def verify_share(run_id: str, token: str) -> bool:
    expected = share_token(run_id)
    return hmac.compare_digest(expected, token or "")


def render_report_html(payload: dict, generated_at: str) -> str:
    data = json.dumps(payload, indent=1).replace("</", "<\\/")
    return _HTML_TEMPLATE.replace("__PAYLOAD__", data).replace("__GENERATED_AT__", generated_at)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TradeMetrix Backtest Report</title>
<style>
  :root { --bg:#0b1220; --panel:#111a2c; --panel2:#16223a; --border:#22304d;
          --fg:#e6edf7; --muted:#8ea0bd; --accent:#38bdf8; --green:#22c55e; --red:#ef4444;
          --amber:#f59e0b; }
  * { box-sizing:border-box; margin:0; padding:0; }
  body { background:var(--bg); color:var(--fg); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }
  .wrap { max-width:1080px; margin:0 auto; padding:28px 20px 80px; }
  header { border-bottom:1px solid var(--border); padding-bottom:16px; margin-bottom:22px; }
  h1 { font-size:22px; letter-spacing:.2px; }
  h1 span { color:var(--accent); }
  .sub { color:var(--muted); font-size:12.5px; margin-top:5px; }
  .actions { margin-top:12px; display:flex; gap:10px; flex-wrap:wrap; }
  .btn { background:var(--panel2); color:var(--fg); border:1px solid var(--border);
         border-radius:8px; padding:8px 14px; font-size:12.5px; cursor:pointer; }
  .btn:hover { border-color:var(--accent); color:var(--accent); }
  .btn.primary { background:var(--accent); border-color:var(--accent); color:#04121f; font-weight:600; }
  section { background:var(--panel); border:1px solid var(--border); border-radius:12px;
            padding:18px; margin-top:18px; }
  h2 { font-size:15px; color:var(--accent); margin-bottom:14px; letter-spacing:.3px; }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }
  .kpi { background:var(--panel2); border:1px solid var(--border); border-radius:10px; padding:10px 12px; }
  .kpi .l { font-size:11px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }
  .kpi .v { font-size:17px; font-weight:700; margin-top:3px; }
  .pos { color:var(--green); } .neg { color:var(--red); }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:8px 22px; }
  .fact { display:flex; justify-content:space-between; gap:14px; padding:7px 2px;
          border-bottom:1px dashed var(--border); font-size:13px; }
  .fact b { color:var(--muted); font-weight:500; }
  .narrative { font-size:13.5px; line-height:1.65; color:var(--fg); max-width:90ch; }
  .narrative b { color:var(--accent); }
  .charts { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media (max-width:760px) { .charts { grid-template-columns:1fr; } }
  .chart-box { background:var(--panel2); border:1px solid var(--border); border-radius:10px; padding:10px; }
  .chart-box .cap { font-size:11.5px; color:var(--muted); margin-bottom:6px; }
  svg text { fill:var(--muted); font-size:10px; }
  .bars { display:flex; gap:14px; flex-wrap:wrap; }
  .bar-col { flex:1; min-width:220px; }
  .bar-row { display:flex; align-items:center; gap:8px; margin:5px 0; font-size:12px; }
  .bar-row .k { width:64px; color:var(--muted); text-align:right; flex-shrink:0; }
  .bar-track { flex:1; background:var(--panel2); border-radius:4px; height:14px; overflow:hidden; }
  .bar-fill { height:100%; background:linear-gradient(90deg,var(--accent),#0ea5e9); border-radius:4px; }
  .table-wrap { overflow-x:auto; }
  table { width:100%; border-collapse:collapse; font-size:12.5px; }
  th, td { padding:7px 10px; text-align:left; border-bottom:1px solid var(--border); white-space:nowrap; }
  th { color:var(--muted); font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:.4px; cursor:pointer; user-select:none; }
  th:hover { color:var(--accent); }
  tr:hover td { background:var(--panel2); }
  .tag { display:inline-block; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:600; }
  .tag.buy { background:rgba(34,197,94,.15); color:var(--green); }
  .tag.sell { background:rgba(239,68,68,.15); color:var(--red); }
  .tag.target { background:rgba(34,197,94,.15); color:var(--green); }
  .tag.stop { background:rgba(239,68,68,.15); color:var(--red); }
  .tag.other { background:rgba(245,158,11,.15); color:var(--amber); }
  .search { background:var(--panel2); color:var(--fg); border:1px solid var(--border);
            border-radius:8px; padding:8px 12px; width:280px; font-size:13px; margin-bottom:12px; }
  .risk-cards { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:14px; }
  footer { margin-top:30px; color:var(--muted); font-size:11.5px; text-align:center; }
  .badge { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11.5px; font-weight:600; margin-left:8px; vertical-align:middle; }
  .badge.ok { background:rgba(34,197,94,.15); color:var(--green); }
  .badge.warn { background:rgba(245,158,11,.15); color:var(--amber); }
  .badge.bad { background:rgba(239,68,68,.15); color:var(--red); }
  @media print { body { background:#fff; color:#111; } section { border-color:#ccc; background:#fff; }
    .btn { display:none; } }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>TradeMetrix <span>Backtest Report</span></h1>
    <div class="sub" id="subline"></div>
    <div class="actions">
      <button class="btn primary" onclick="window.print()">Print / Save PDF</button>
      <button class="btn" onclick="copyLink()">Copy link</button>
    </div>
  </header>

  <section id="summary-sec">
    <h2>Executive Summary</h2>
    <p class="narrative" id="narrative"></p>
  </section>

  <section id="kpi-sec">
    <h2>Performance</h2>
    <div class="kpis" id="kpis"></div>
  </section>

  <section>
    <h2>Strategy Fact Sheet</h2>
    <div class="grid" id="factsheet"></div>
  </section>

  <section>
    <h2>Equity &amp; Drawdown</h2>
    <div class="charts">
      <div class="chart-box"><div class="cap">Equity curve</div><div id="equity-chart"></div></div>
      <div class="chart-box"><div class="cap">Drawdown %</div><div id="dd-chart"></div></div>
    </div>
    <div class="bars" style="margin-top:14px">
      <div class="bar-col" id="weekday-bars"></div>
      <div class="bar-col" id="hour-bars"></div>
    </div>
  </section>

  <section id="risk-sec" style="display:none">
    <h2>Risk Analytics</h2>
    <div class="risk-cards" id="risk-cards"></div>
    <div class="bars">
      <div class="bar-col" id="rej-bars"></div>
    </div>
    <h2 style="margin-top:16px">Rejected Orders</h2>
    <div class="table-wrap" id="rej-table"></div>
  </section>

  <section>
    <h2>Trades <span id="trade-count" class="sub"></span></h2>
    <input class="search" id="trade-search" type="search" placeholder="Search trades (symbol, side, reason)">
    <div class="table-wrap" id="trades-table"></div>
  </section>

  <footer>Read-only report generated by TradeMetrix &middot; <span id="footer-date"></span></footer>
</div>

<script>
(function () {
  var RUN = __PAYLOAD__;
  var c = RUN.config || {};
  var fmt = function (v, d) { return (v == null || isNaN(v)) ? "&mdash;" : Number(v).toFixed(d == null ? 2 : d); };
  var signCls = function (v) { return v > 0 ? "pos" : (v < 0 ? "neg" : ""); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (m) {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]; }); };

  document.getElementById("subline").innerHTML =
    "Run " + esc(RUN.run_id) + " &middot; " + esc(c.strategy_type || "strategy") +
    " &middot; " + esc(c.symbol || "NIFTY") + " " + esc(c.interval || "") +
    " &middot; " + esc(c.days) + "d window &middot; " + esc(RUN.status || "") +
    " &middot; generated " + esc("__GENERATED_AT__");
  document.getElementById("footer-date").textContent = new Date("__GENERATED_AT__").toLocaleString();

  var narrative = [];
  narrative.push("This backtest of the <b>" + esc(c.strategy_type || "unknown") + "</b> strategy on <b>" +
    esc(c.symbol || "NIFTY") + " " + esc(c.interval || "") + "</b> over <b>" + esc(c.days) + "</b> trading days " +
    "(" + esc(RUN.candles_analyzed || 0) + " candles, initial capital " + fmt(RUN.start_equity, 0) + ") " +
    "closed " + esc(RUN.total_trades || 0) + " trades with a net P&L of <b class='" + signCls(RUN.net_pnl) + "'>" +
    fmt(RUN.net_pnl) + "</b> (" + fmt(RUN.return_pct) + "% return), " +
    "win rate " + fmt(RUN.win_rate) + "%, profit factor " + fmt(RUN.profit_factor) + ".");
  narrative.push("The equity curve peaked at " + fmt(RUN.end_equity + Math.abs(RUN.max_drawdown), 0) +
    " and gave back at most " + fmt(RUN.max_drawdown_pct) + "% at the deepest drawdown. " +
    "Sharpe " + fmt(RUN.sharpe_ratio) + ", Sortino " + fmt(RUN.sortino_ratio) + ", Calmar " + fmt(RUN.calmar_ratio) +
    ", expectancy " + fmt(RUN.expectancy) + " per trade with an average risk/reward of " +
    fmt(RUN.avg_risk_reward_ratio) + ".");
  if (RUN.benchmark_return_pct) {
    narrative.push("Against the benchmark (" + fmt(RUN.benchmark_return_pct) + "% return) the strategy produced " +
      fmt(RUN.alpha) + " alpha at a beta of " + fmt(RUN.beta) + " (" + fmt(RUN.excess_return_pct) + "% excess return).");
  }
  if (RUN.winning_trades && RUN.losing_trades) {
    narrative.push("The best trade made " + fmt(RUN.largest_win) + ", the worst lost " + fmt(RUN.largest_loss) +
      ", and the average winner (" + fmt(RUN.avg_win) + ") out-earned the average loser (" + fmt(RUN.avg_loss) +
      ") by a factor of " + (RUN.avg_loss ? fmt(RUN.avg_win / Math.abs(RUN.avg_loss)) : "&infin;") + ".");
  }
  var verdict, badge;
  if (RUN.net_pnl > 0 && RUN.win_rate >= 50) { verdict = "profitable and consistent"; badge = "ok"; }
  else if (RUN.net_pnl > 0) { verdict = "profitable but inconsistent"; badge = "warn"; }
  else { verdict = "not profitable in this window"; badge = "bad"; }
  narrative.push("Verdict: the strategy is <b>" + verdict + "</b> over this window." +
    '<span class="badge ' + badge + '">' + (badge === "ok" ? "PASS" : badge === "warn" ? "CAUTION" : "FAIL") + "</span>");
  document.getElementById("narrative").innerHTML = narrative.join(" ");

  var kpis = [
    ["Net P&L", fmt(RUN.net_pnl), signCls(RUN.net_pnl)],
    ["Return", fmt(RUN.return_pct) + "%", signCls(RUN.return_pct)],
    ["Trades", String(RUN.total_trades || 0), ""],
    ["Win Rate", fmt(RUN.win_rate) + "%", ""],
    ["Profit Factor", fmt(RUN.profit_factor), ""],
    ["Expectancy", fmt(RUN.expectancy), signCls(RUN.expectancy)],
    ["Max Drawdown", fmt(RUN.max_drawdown_pct) + "%", "neg"],
    ["Sharpe", fmt(RUN.sharpe_ratio), ""],
    ["Sortino", fmt(RUN.sortino_ratio), ""],
    ["Calmar", fmt(RUN.calmar_ratio), ""],
    ["Avg Risk/Reward", fmt(RUN.avg_risk_reward_ratio), ""],
    ["End Equity", fmt(RUN.end_equity, 0), ""],
  ];
  var kpiHtml = "";
  kpis.forEach(function (k) {
    kpiHtml += '<div class="kpi"><div class="l">' + k[0] + '</div><div class="v ' + k[2] + '">' + k[1] + "</div></div>";
  });
  document.getElementById("kpis").innerHTML = kpiHtml;

  var facts = [
    ["Strategy", c.strategy_type || "&mdash;"], ["Strategy ID", c.strategy_id || "&mdash;"],
    ["Symbol / Exchange", esc(c.symbol || "NIFTY") + " / " + esc(c.exchange || "NSE")],
    ["Interval / Window", esc(c.interval || "") + " / " + esc(c.days) + " days"],
    ["Initial Capital", fmt(RUN.start_equity, 0)],
    ["Data Source", esc(c.data_source || "auto")],
    ["Risk Checks", c.risk_enabled ? "Enabled" : "Disabled"],
    ["Close On End", c.close_positions_on_end ? "Yes" : "No"],
    ["Slippage", fmt(c.slippage_pct) + "%"], ["Latency", esc(c.latency_candles) + " candles"],
    ["Partial Fills", fmt(c.partial_fill_probability * 100) + "%"],
    ["Speed", esc(c.speed || "MAX")],
    ["Candles Analyzed", String(RUN.candles_analyzed || 0)],
    ["Total Fees", fmt(RUN.total_fees)],
    ["Avg Trade Duration", fmt(RUN.average_trade_duration_minutes) + " min"],
    ["Started", esc(RUN.started_at || "&mdash;")], ["Completed", esc(RUN.completed_at || "&mdash;")],
    ["Run Duration", fmt(RUN.duration_seconds) + "s"],
  ];
  var factHtml = "";
  facts.forEach(function (f) { factHtml += '<div class="fact"><b>' + f[0] + "</b><span>" + f[1] + "</span></div>"; });
  document.getElementById("factsheet").innerHTML = factHtml;

  function lineChart(elId, values, opts) {
    var el = document.getElementById(elId);
    if (!el || !values || values.length < 2) { el.innerHTML = '<div style="color:var(--muted);font-size:12px">Insufficient data</div>'; return; }
    var W = 820, H = 230, padL = 62, padR = 14, padT = 12, padB = 24;
    var min = Infinity, max = -Infinity;
    values.forEach(function (v) { if (v < min) min = v; if (v > max) max = v; });
    var span = max - min || 1; min -= span * 0.05; max += span * 0.05;
    var x = function (i) { return padL + (i / (values.length - 1)) * (W - padL - padR); };
    var y = function (v) { return padT + (1 - (v - min) / (max - min)) * (H - padT - padB); };
    var pts = values.map(function (v, i) { return x(i) + "," + y(v); }).join(" ");
    var grid = "", labels = "";
    for (var g = 0; g <= 4; g++) {
      var gy = padT + (g / 4) * (H - padT - padB), gv = max - (g / 4) * (max - min);
      grid += '<line x1="' + padL + '" y1="' + gy + '" x2="' + (W - padR) + '" y2="' + gy +
        '" stroke="#22304d" stroke-width="1"/>';
      labels += '<text x="' + (padL - 8) + '" y="' + (gy + 3) + '" text-anchor="end">' + fmt(gv, 0) + "</text>";
    }
    var area = opts && opts.area ? '<polygon points="' + padL + "," + (H - padB) + " " + pts + " " +
      x(values.length - 1) + "," + (H - padB) + '" fill="' + (opts.area || "none") + '"/>' : "";
    el.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" style="max-width:100%;height:auto">' +
      grid + labels + area +
      '<polyline points="' + pts + '" fill="none" stroke="' + (opts.color || "#38bdf8") +
      '" stroke-width="1.8" stroke-linejoin="round"/>' +
      '<text x="' + padL + '" y="' + (H - 6) + '" font-size="10" fill="#8ea0bd">1</text>' +
      '<text x="' + (W - padR - 6) + '" y="' + (H - 6) + '" text-anchor="end" font-size="10" fill="#8ea0bd">' +
      values.length + "</text></svg>";
  }
  var eq = (RUN.equity_curve || []).map(function (e) { return typeof e === "number" ? e : e.equity; });
  var dd = (RUN.equity_curve || []).map(function (e) { return typeof e === "number" ? 0 : (e.drawdown_pct || 0); });
  lineChart("equity-chart", eq, { color: "#38bdf8", area: "rgba(56,189,248,0.12)" });
  lineChart("dd-chart", dd, { color: "#ef4444", area: "rgba(239,68,68,0.12)" });

  function bars(elId, dist, labels) {
    var el = document.getElementById(elId);
    if (!el || !dist) return;
    var entries = Object.keys(dist).sort(function (a, b) {
      var ia = labels ? labels.indexOf(a) : -1, ib = labels ? labels.indexOf(b) : -1;
      return (ia >= 0 && ib >= 0) ? ia - ib : (a < b ? -1 : 1);
    });
    var max = 0; entries.forEach(function (k) { if (dist[k] > max) max = dist[k]; });
    if (!max) { el.innerHTML = '<div class="cap">No data</div>'; return; }
    var html = '<div class="cap">' + (labels ? "Weekday distribution" : "Hour distribution") + "</div>";
    entries.forEach(function (k) {
      html += '<div class="bar-row"><span class="k">' + esc(k) + '</span><div class="bar-track"><div class="bar-fill" style="width:' +
        Math.max(3, (dist[k] / max) * 100) + '%"></div></div><span style="color:var(--muted);font-size:11px">' +
        fmt(dist[k]) + "</span></div>";
    });
    el.innerHTML = html;
  }
  bars("weekday-bars", RUN.weekday_distribution, ["Mon", "Tue", "Wed", "Thu", "Fri"]);
  bars("hour-bars", RUN.hour_distribution, null);

  var ra = RUN.risk_analytics;
  if (ra && ra.enabled) {
    document.getElementById("risk-sec").style.display = "";
    var rc = [
      ["Accepted", String(ra.accepted_trades || 0)], ["Rejected", String(ra.rejected_trades || 0)],
      ["Breach Halts", String(ra.halt_count || 0)],
      ["Rules Fired", String(Object.keys(ra.rejection_reasons || {}).length || 0)],
    ];
    var rcHtml = "";
    rc.forEach(function (k) { rcHtml += '<div class="kpi"><div class="l">' + k[0] + '</div><div class="v">' + k[1] + "</div></div>"; });
    document.getElementById("risk-cards").innerHTML = rcHtml;
    var rej = ra.rejections || [];
    var byRule = {};
    rej.forEach(function (r) { byRule[r.rule] = (byRule[r.rule] || 0) + 1; });
    var rejMax = 0; Object.keys(byRule).forEach(function (k) { if (byRule[k] > rejMax) rejMax = byRule[k]; });
    var rejHtml = '<div class="cap">Rejections by rule</div>';
    Object.keys(byRule).sort().forEach(function (k) {
      rejHtml += '<div class="bar-row"><span class="k">' + esc(k) + '</span><div class="bar-track"><div class="bar-fill" style="width:' +
        Math.max(3, (byRule[k] / rejMax) * 100) + '%"></div></div><span style="color:var(--muted);font-size:11px">' +
        byRule[k] + "</span></div>";
    });
    document.getElementById("rej-bars").innerHTML = rejHtml || '<div class="cap">No rejections</div>';
    var head = "<tr><th>Time</th><th>Symbol</th><th>Side</th><th>Qty</th><th>Price</th><th>Rule</th><th>Reason</th></tr>";
    var rows = rej.slice(0, 200).map(function (r) {
      return "<tr><td>" + esc(r.timestamp) + "</td><td>" + esc(r.symbol) + "</td><td>" + esc(r.side) +
        "</td><td>" + esc(r.quantity) + "</td><td>" + fmt(r.price) + "</td><td>" + esc(r.rule) +
        "</td><td>" + esc(r.reason) + "</td></tr>";
    }).join("");
    document.getElementById("rej-table").innerHTML =
      "<table><thead>" + head + "</thead><tbody>" + (rows || "<tr><td colspan=7>No rejections</td></tr>") +
      "</tbody></table>" + (rej.length > 200 ? '<div class="sub" style="margin-top:8px">Showing 200 of ' + rej.length + "</div>" : "");
  }

  var trades = RUN.trades || [];
  document.getElementById("trade-count").textContent = trades.length + " trades";
  var cols = [
    ["no", "#", function (t, i) { return String(i + 1); }],
    ["symbol", "Symbol", function (t) { return esc(t.symbol); }],
    ["side", "Side", function (t) {
      var s = (t.side || "?").toLowerCase();
      return '<span class="tag ' + (s === "buy" ? "buy" : "sell") + '">' + esc(t.side) + "</span>";
    }],
    ["entry_price", "Entry", function (t) { return fmt(t.entry_price); }],
    ["exit_price", "Exit", function (t) { return fmt(t.exit_price); }],
    ["quantity", "Qty", function (t) { return String(t.quantity); }],
    ["pnl", "P&L", function (t) { return '<span class="' + signCls(t.pnl) + '">' + fmt(t.pnl) + "</span>"; }],
    ["risk_reward_ratio", "R:R", function (t) { return t.risk_reward_ratio != null ? fmt(t.risk_reward_ratio) : "&mdash;"; }],
    ["entry_reason", "Entry", function (t) { return esc(t.entry_reason || "&mdash;"); }],
    ["exit_reason", "Exit", function (t) {
      var r = t.exit_reason || "";
      return '<span class="tag ' + (r === "target" ? "target" : r === "stop_loss" ? "stop" : "other") + '">' + esc(r || "&mdash;") + "</span>";
    }],
    ["entry_time", "Entry Time", function (t) { return esc(t.entry_time || "&mdash;"); }],
    ["exit_time", "Exit Time", function (t) { return esc(t.exit_time || "&mdash;"); }],
  ];
  function renderTrades(rows) {
    var head = "<tr>" + cols.map(function (k) { return "<th data-k='" + k[0] + "'>" + k[1] + "</th>"; }).join("") + "</tr>";
    var body = rows.map(function (t, i) {
      return "<tr>" + cols.map(function (k) { return "<td>" + k[2](t, i) + "</td>"; }).join("") + "</tr>";
    }).join("");
    document.getElementById("trades-table").innerHTML =
      "<table><thead>" + head + "</thead><tbody>" + (body || "<tr><td colspan=" + cols.length + ">No trades</td></tr>") + "</tbody></table>";
  }
  var q = "";
  document.getElementById("trade-search").addEventListener("input", function (e) {
    q = e.target.value.toLowerCase();
    renderTrades(trades.filter(function (t) {
      return !q || [t.symbol, t.side, t.entry_reason, t.exit_reason, t.entry_time, t.exit_time]
        .join(" ").toLowerCase().indexOf(q) >= 0;
    }));
  });
  document.getElementById("trades-table").addEventListener("click", function (e) {
    var th = e.target.closest("th"); if (!th) return;
    var k = th.dataset.k, idx = cols.findIndex(function (x) { return x[0] === k; });
    var sorted = trades.slice().sort(function (a, b) {
      var av = a[cols[idx][0]], bv = b[cols[idx][0]];
      if (typeof av === "number" && typeof bv === "number") return av - bv;
      return String(av).localeCompare(String(bv));
    });
    renderTrades(sorted);
  });
  renderTrades(trades);

  window.copyLink = function () {
    if (navigator.clipboard) navigator.clipboard.writeText(window.location.href);
    var btn = event.target; var old = btn.textContent; btn.textContent = "Copied!"; btn.classList.add("primary");
    setTimeout(function () { btn.textContent = old; btn.classList.remove("primary"); }, 1200);
  };
})();
</script>
</body>
</html>
"""
