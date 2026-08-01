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


def export_pdf(result: BacktestResult) -> bytes:
    if not _REPORTLAB:
        raise RuntimeError("reportlab is not installed; cannot export PDF")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), leftMargin=15 * mm,
                            rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("TitleSmall", parent=styles["Title"], fontSize=16)
    h3 = ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11)

    story = [
        Paragraph(f"Backtest Report — {result.run_id}", title),
        Spacer(1, 4 * mm),
        Paragraph(
            f"Strategy: {result.config.strategy_type if result.config else ''} | "
            f"Symbol: {result.config.symbol if result.config else ''} | "
            f"Interval: {result.config.interval if result.config else ''}",
            h3,
        ),
        Spacer(1, 3 * mm),
    ]

    summary_rows = [
        ["Net PnL", f"{result.net_pnl:.2f}", "Return", f"{result.return_pct:.2f}%",
         "Win Rate", f"{result.win_rate:.2f}%"],
        ["Trades", str(result.total_trades), "Profit Factor", f"{result.profit_factor:.2f}",
         "Expectancy", f"{result.expectancy:.2f}"],
        ["Max Drawdown", f"{result.max_drawdown_pct:.2f}%", "Sharpe", f"{result.sharpe_ratio:.2f}",
         "Sortino", f"{result.sortino_ratio:.2f}"],
        ["Benchmark Return", f"{result.benchmark_return_pct:.2f}%", "Alpha", f"{result.alpha:.2f}",
         "Beta", f"{result.beta:.2f}"],
        ["Start Equity", f"{result.start_equity:.2f}", "End Equity", f"{result.end_equity:.2f}",
         "Duration (s)", f"{result.duration_seconds:.1f}"],
    ]
    summary_table = Table(summary_rows, colWidths=[28 * mm] * 6)
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (0, -1), colors.lightgrey),
        ("BACKGROUND", (2, 0), (2, -1), colors.lightgrey),
        ("BACKGROUND", (4, 0), (4, -1), colors.lightgrey),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 4 * mm))

    if result.trades:
        story.append(Paragraph("Trades", h3))
        trade_rows = [["#", "Symbol", "Side", "Entry", "Exit", "Qty", "PnL"]]
        for i, t in enumerate(result.trades, 1):
            trade_rows.append([str(i), t.symbol, t.side, f"{t.entry_price:.2f}",
                               f"{t.exit_price:.2f}", str(t.quantity), f"{t.pnl:.2f}"])
        trade_table = Table(trade_rows, colWidths=[8 * mm, 25 * mm, 15 * mm,
                                                   20 * mm, 20 * mm, 15 * mm, 22 * mm])
        trade_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(trade_table)

    doc.build(story)
    return buf.getvalue()
