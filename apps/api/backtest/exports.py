"""Backtest result exports: JSON, CSV (trades + equity), PDF (reportlab)."""
from __future__ import annotations

import csv
import io
import json

from backtest.models import BacktestResult

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    _REPORTLAB = True
except ImportError:
    _REPORTLAB = False


def export_json(result: BacktestResult) -> str:
    payload = {
        "run_id": result.run_id,
        "status": result.status.value,
        "config": result.config.model_dump(mode="json") if result.config else {},
        "summary": {
            "total_trades": result.total_trades,
            "winning_trades": result.winning_trades,
            "losing_trades": result.losing_trades,
            "win_rate": result.win_rate,
            "net_pnl": result.net_pnl,
            "profit_factor": result.profit_factor,
            "max_drawdown_pct": result.max_drawdown_pct,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "return_pct": result.return_pct,
            "expectancy": result.expectancy,
            "avg_risk_reward_ratio": result.avg_risk_reward_ratio,
            "alpha": result.alpha,
            "beta": result.beta,
            "benchmark_return_pct": result.benchmark_return_pct,
            "start_equity": result.start_equity,
            "end_equity": result.end_equity,
        },
        "trades": [t.model_dump(mode="json") for t in result.trades],
        "equity_curve": [
            e.model_dump(mode="json") if hasattr(e, "model_dump") else e
            for e in result.equity_curve
        ],
        "weekday_distribution": result.weekday_distribution,
        "hour_distribution": result.hour_distribution,
        "month_distribution": result.month_distribution,
        "started_at": result.started_at,
        "completed_at": result.completed_at,
        "duration_seconds": result.duration_seconds,
    }
    return json.dumps(payload, indent=2)


def export_csv(result: BacktestResult) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["run_id", result.run_id])
    writer.writerow(["net_pnl", result.net_pnl])
    writer.writerow(["return_pct", result.return_pct])
    writer.writerow(["win_rate", result.win_rate])
    writer.writerow(["max_drawdown_pct", result.max_drawdown_pct])
    writer.writerow(["sharpe_ratio", result.sharpe_ratio])
    writer.writerow(["expectancy", result.expectancy])
    writer.writerow(["alpha", result.alpha])
    writer.writerow(["beta", result.beta])
    writer.writerow([])
    writer.writerow(["trade_no", "symbol", "side", "entry_price", "exit_price",
                     "quantity", "pnl", "entry_time", "exit_time"])
    for i, t in enumerate(result.trades, 1):
        writer.writerow([i, t.symbol, t.side, t.entry_price, t.exit_price,
                         t.quantity, t.pnl, t.entry_time, t.exit_time])
    writer.writerow([])
    writer.writerow(["timestamp", "equity", "drawdown", "drawdown_pct"])
    for e in result.equity_curve:
        if hasattr(e, "model_dump"):
            writer.writerow([e.timestamp, e.equity, e.drawdown, e.drawdown_pct])
        else:
            writer.writerow([e.get("timestamp", ""), e.get("equity", ""),
                             e.get("drawdown", ""), e.get("drawdown_pct", "")])
    return buf.getvalue()


_ACCENT = colors.HexColor("#0284c7")
_HEAD = colors.HexColor("#0f172a")
_GOOD = colors.HexColor("#16a34a")
_BAD = colors.HexColor("#dc2626")


def _pdf_chart(values: list, stroke: str, fill: str) -> "object | None":
    """Return a reportlab Drawing with a single line series, or None."""
    if not _REPORTLAB or not values or len(values) < 2:
        return None
    try:
        from reportlab.graphics.charts.lineplots import LinePlot
        from reportlab.graphics.shapes import Drawing

        d = Drawing(460, 150)
        lp = LinePlot()
        lp.x = 42
        lp.y = 24
        lp.width = 402
        lp.height = 112
        lp.data = [[(i, float(v)) for i, v in enumerate(values)]]
        lp.lines[0].strokeColor = colors.HexColor(stroke)
        lp.lines[0].strokeWidth = 1.4
        lp.yValueAxis.labelTextFormat = "%0.0f"
        lp.xValueAxis.visibleTicks = 0
        lp.xValueAxis.labels.fontSize = 7
        lp.yValueAxis.labels.fontSize = 7
        d.add(lp)
        return d
    except Exception:
        return None


def _exec_narrative(result: BacktestResult) -> list[str]:
    cfg = result.config
    out = [
        (f"This backtest of the <b>{cfg.strategy_type or 'unknown'}</b> strategy on "
         f"<b>{cfg.symbol or 'NIFTY'} {cfg.interval or ''}</b> over <b>{cfg.days}</b> trading days "
         f"({result.candles_analyzed} candles analyzed, initial capital "
         f"{result.start_equity:,.0f}) closed <b>{result.total_trades}</b> trades with a net "
         f"P&amp;L of <b>{result.net_pnl:,.2f}</b> ({result.return_pct:.2f}% return), a win rate of "
         f"{result.win_rate:.2f}% and a profit factor of {result.profit_factor:.2f}.")
    ]
    out.append(
        f"The equity curve peaked at {result.end_equity - result.max_drawdown:,.0f} and gave back at "
        f"most {result.max_drawdown_pct:.2f}% at the deepest drawdown, with a Sharpe of "
        f"{result.sharpe_ratio:.2f}, Sortino of {result.sortino_ratio:.2f} and Calmar of "
        f"{result.calmar_ratio:.2f}. Expectancy was {result.expectancy:,.2f} per trade at an average "
        f"risk/reward of {result.avg_risk_reward_ratio:.2f}."
    )
    if result.benchmark_return_pct:
        out.append(
            f"Against the benchmark ({result.benchmark_return_pct:.2f}% return) the strategy produced "
            f"{result.alpha:.2f} alpha at a beta of {result.beta:.2f} "
            f"({result.excess_return_pct:.2f}% excess return)."
        )
    if result.winning_trades and result.losing_trades:
        out.append(
            f"The best trade made {result.largest_win:,.2f}, the worst lost {result.largest_loss:,.2f}, "
            f"and the average winner ({result.avg_win:,.2f}) out-earned the average loser "
            f"({result.avg_loss:,.2f})."
        )
    if result.net_pnl > 0 and result.win_rate >= 50:
        verdict = "profitable and consistent (PASS)"
    elif result.net_pnl > 0:
        verdict = "profitable but inconsistent (CAUTION)"
    else:
        verdict = "not profitable in this window (FAIL)"
    out.append(f"<b>Verdict: the strategy is {verdict} over this window.</b>")
    return out


def export_pdf(result: BacktestResult) -> bytes:
    if not _REPORTLAB:
        raise RuntimeError("reportlab is not installed; cannot export PDF")

    from datetime import datetime, timezone

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm)

    def _footer(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(14 * mm, 8 * mm,
                          f"TradeMetrix Backtest Report — {result.run_id} — generated "
                          f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · read-only")
        canvas.drawRightString(A4[0] - 14 * mm, 8 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleMain", parent=styles["Title"], fontSize=17,
                           textColor=_HEAD, spaceAfter=2)
    subtitle = ParagraphStyle("Subtitle", parent=styles["Normal"], fontSize=8.5,
                              textColor=colors.grey, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12,
                        textColor=_ACCENT, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=8.8, leading=12.5)
    caption = ParagraphStyle("Caption", parent=styles["Normal"], fontSize=7.5, textColor=colors.grey)
    kpi_lbl = ParagraphStyle("KpiLbl", parent=styles["Normal"], fontSize=7.5,
                             textColor=colors.grey, alignment=1)
    kpi_val = ParagraphStyle("KpiVal", parent=styles["Normal"], fontSize=9.5,
                             textColor=_HEAD, alignment=1)

    cfg = result.config
    story = [
        Paragraph("TradeMetrix — Institutional Backtest Report", title),
        Paragraph(
            f"Run {result.run_id} · {cfg.strategy_type or 'strategy'} · "
            f"{cfg.symbol or 'NIFTY'} {cfg.interval or ''} · {cfg.days} days · "
            f"status {result.status.value}",
            subtitle,
        ),
    ]

    story.append(Paragraph("Executive Summary", h2))
    for p in _exec_narrative(result):
        story.append(Paragraph(p, body))
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Performance", h2))
    kpi_pairs = [
        ("Net P&L", f"{result.net_pnl:,.2f}", "Return", f"{result.return_pct:.2f}%"),
        ("Trades", str(result.total_trades), "Win Rate", f"{result.win_rate:.2f}%"),
        ("Winning / Losing", f"{result.winning_trades} / {result.losing_trades}",
         "Profit Factor", f"{result.profit_factor:.2f}"),
        ("Max Drawdown", f"{result.max_drawdown_pct:.2f}%", "Sharpe", f"{result.sharpe_ratio:.2f}"),
        ("Sortino", f"{result.sortino_ratio:.2f}", "Calmar", f"{result.calmar_ratio:.2f}"),
        ("Expectancy", f"{result.expectancy:,.2f}", "Avg Risk/Reward", f"{result.avg_risk_reward_ratio:.2f}"),
        ("Benchmark Return", f"{result.benchmark_return_pct:.2f}%", "Alpha / Beta", f"{result.alpha:.2f} / {result.beta:.2f}"),
        ("Start Equity", f"{result.start_equity:,.2f}", "End Equity", f"{result.end_equity:,.2f}"),
        ("Candles Analyzed", str(result.candles_analyzed), "Duration", f"{result.duration_seconds:.1f}s"),
    ]
    kpi_rows = []
    for lbl1, val1, lbl2, val2 in kpi_pairs:
        kpi_rows.append([Paragraph(lbl1, kpi_lbl), Paragraph(val1, kpi_val),
                         Paragraph(lbl2, kpi_lbl), Paragraph(val2, kpi_val)])
    kpi_table = Table(kpi_rows, colWidths=[34 * mm, 57 * mm, 34 * mm, 57 * mm])
    kpi_style = TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])
    kpi_table.setStyle(kpi_style)
    story.append(kpi_table)
    story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Equity &amp; Drawdown", h2))
    eq_curve = result.equity_curve or []
    eq = [float(e.equity) if hasattr(e, "equity") else float(e["equity"]) for e in eq_curve]
    dd = [float(e.drawdown_pct or 0.0) if hasattr(e, "drawdown_pct")
          else float(e.get("drawdown_pct") or 0.0) for e in eq_curve]
    eq_chart = _pdf_chart(eq, "#0284c7", None)
    dd_chart = _pdf_chart(dd, "#dc2626", None)
    if eq_chart is not None and dd_chart is not None:
        story.append(eq_chart)
        story.append(Paragraph("Equity curve", caption))
        story.append(Spacer(1, 2 * mm))
        story.append(dd_chart)
        story.append(Paragraph("Drawdown %", caption))

    if result.monthly_returns:
        story.append(Paragraph("Monthly Returns", h2))
        mrows = [["Month", "Return %"]] + [
            [m, f"{v:.2f}"] for m, v in sorted(result.monthly_returns.items())
        ]
        mtable = Table(mrows, colWidths=[50 * mm, 50 * mm], repeatRows=1)
        mtable.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ]))
        story.append(mtable)

    ra = result.risk_analytics
    if ra and ra.enabled:
        story.append(Paragraph("Risk Analytics", h2))
        risk_pairs = [
            ("Accepted / Rejected", f"{ra.accepted_trades} / {ra.rejected_trades}",
             "Breach Halts", str(ra.halt_count)),
            ("Timeline Points", str(len(ra.timeline)),
             "Rules Fired", ", ".join(sorted(ra.rejection_reasons.keys())) or "—"),
        ]
        risk_rows = []
        for lbl1, val1, lbl2, val2 in risk_pairs:
            risk_rows.append([Paragraph(lbl1, kpi_lbl), Paragraph(val1, kpi_val),
                              Paragraph(lbl2, kpi_lbl), Paragraph(val2, kpi_val)])
        risk_table = Table(risk_rows, colWidths=[34 * mm, 57 * mm, 34 * mm, 57 * mm])
        risk_table.setStyle(kpi_style)
        story.append(risk_table)
        rej = list(ra.rejections or [])
        if rej:
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(f"Rejected Orders ({len(rej)}, showing up to 200)", h2))
            rej_rows = [["Time", "Symbol", "Side", "Qty", "Price", "Rule", "Reason"]]
            for r in rej[:200]:
                rej_rows.append([str(r.timestamp), str(r.symbol), str(r.side), str(r.quantity),
                                 f"{r.price:.2f}", str(r.rule), str(r.reason)])
            rej_table = Table(rej_rows, repeatRows=1,
                              colWidths=[30 * mm, 24 * mm, 10 * mm, 10 * mm, 15 * mm, 27 * mm, 66 * mm])
            rej_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
            ]))
            story.append(rej_table)

    if result.trades:
        story.append(Paragraph("Trades", h2))
        trade_rows = [["#", "Symbol", "Side", "Entry", "Exit", "Qty", "P&L", "R:R", "Entry Reason", "Exit Reason"]]
        for i, t in enumerate(result.trades, 1):
            trade_rows.append([str(i), t.symbol, t.side, f"{t.entry_price:.2f}", f"{t.exit_price:.2f}",
                               str(t.quantity), f"{t.pnl:,.2f}",
                               f"{t.rr:.2f}" if getattr(t, "rr", 0) else "—",
                               str(getattr(t, "entry_reason", "") or "—"),
                               str(getattr(t, "exit_reason", "") or "—")])
        trade_table = Table(trade_rows, repeatRows=1,
                            colWidths=[8 * mm, 22 * mm, 12 * mm, 17 * mm, 17 * mm,
                                       12 * mm, 20 * mm, 12 * mm, 31 * mm, 31 * mm])
        trade_style = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 6.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
        ]
        for i, t in enumerate(result.trades, 1):
            if t.pnl > 0:
                trade_style.append(("TEXTCOLOR", (6, i), (6, i), _GOOD))
            elif t.pnl < 0:
                trade_style.append(("TEXTCOLOR", (6, i), (6, i), _BAD))
        trade_table.setStyle(TableStyle(trade_style))
        story.append(trade_table)

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buf.getvalue()
