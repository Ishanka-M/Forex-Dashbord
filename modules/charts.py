"""
modules/charts.py
Plotly Chart Builder for FX-WavePulse Pro
"""

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from modules.elliott_wave import ElliottWaveResult
from modules.smc_analysis import SMCResult

CHART_THEME = {
    "bg": "#0A0E1A",
    "grid": "#1A2035",
    "text": "#E0E6F0",
    "bull": "#00D4AA",
    "bear": "#FF4B6E",
    "neutral": "#6B8CAE",
    "wave": "#FFD700",
    "ob_bull": "rgba(0, 212, 170, 0.15)",
    "ob_bear": "rgba(255, 75, 110, 0.15)",
    "fvg_bull": "rgba(100, 200, 255, 0.12)",
    "fvg_bear": "rgba(255, 180, 100, 0.12)",
    "fib": "#8B5CF6",
}


def create_candlestick_chart(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    ew_result: ElliottWaveResult = None,
    smc_result: SMCResult = None,
    show_volume: bool = True
) -> go.Figure:
    """Create a full analysis chart with EW waves and SMC zones."""
    
    rows = 2 if show_volume else 1
    row_heights = [0.75, 0.25] if show_volume else [1.0]
    
    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=[f"{symbol} / {timeframe}", "Volume"] if show_volume else [f"{symbol} / {timeframe}"]
    )

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df["open"],
        high=df["high"],
        low=df["low"],
        close=df["close"],
        name="Price",
        increasing_line_color=CHART_THEME["bull"],
        decreasing_line_color=CHART_THEME["bear"],
        increasing_fillcolor=CHART_THEME["bull"],
        decreasing_fillcolor=CHART_THEME["bear"],
    ), row=1, col=1)

    # SMC Zones
    if smc_result:
        _add_smc_zones(fig, df, smc_result)

    # Elliott Wave overlays
    if ew_result and ew_result.wave_points:
        _add_elliott_wave(fig, df, ew_result)
        _add_fibonacci_levels(fig, df, ew_result)

    # Volume bars
    if show_volume and "volume" in df.columns:
        colors = [CHART_THEME["bull"] if c >= o else CHART_THEME["bear"]
                  for c, o in zip(df["close"], df["open"])]
        fig.add_trace(go.Bar(
            x=df.index,
            y=df["volume"],
            name="Volume",
            marker_color=colors,
            opacity=0.6,
        ), row=2, col=1)

    # Current price line
    current_price = df["close"].iloc[-1]
    fig.add_hline(
        y=current_price,
        line_dash="dash",
        line_color="#FFFFFF",
        line_width=1,
        annotation_text=f"  {current_price:.5f}",
        annotation_font_color="#FFFFFF",
        row=1, col=1
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_THEME["bg"],
        plot_bgcolor=CHART_THEME["bg"],
        font=dict(color=CHART_THEME["text"], family="JetBrains Mono, monospace", size=11),
        xaxis_rangeslider_visible=False,
        height=600,
        margin=dict(l=10, r=10, t=40, b=10),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor="rgba(0,0,0,0.5)"
        ),
        xaxis=dict(gridcolor=CHART_THEME["grid"], showgrid=True),
        yaxis=dict(gridcolor=CHART_THEME["grid"], showgrid=True),
    )

    return fig


def _add_smc_zones(fig: go.Figure, df: pd.DataFrame, smc: SMCResult):
    """Add SMC Order Blocks, FVGs, and Structure to chart."""
    
    # Order Blocks
    for ob in smc.order_blocks:
        if ob.is_mitigated:
            continue
        color = CHART_THEME["ob_bull"] if ob.ob_type == "bullish" else CHART_THEME["ob_bear"]
        border_color = CHART_THEME["bull"] if ob.ob_type == "bullish" else CHART_THEME["bear"]
        
        fig.add_hrect(
            y0=ob.bottom, y1=ob.top,
            fillcolor=color,
            line=dict(color=border_color, width=0.5),
            annotation_text=f"{'🟢' if ob.ob_type == 'bullish' else '🔴'} OB",
            annotation_font_color=border_color,
            annotation_font_size=9,
            row=1, col=1
        )

    # Fair Value Gaps
    for fvg in smc.fair_value_gaps[:5]:
        if fvg.is_filled:
            continue
        color = CHART_THEME["fvg_bull"] if fvg.fvg_type == "bullish" else CHART_THEME["fvg_bear"]
        border_color = "#64C8FF" if fvg.fvg_type == "bullish" else "#FFB464"
        
        fig.add_hrect(
            y0=fvg.bottom, y1=fvg.top,
            fillcolor=color,
            line=dict(color=border_color, width=0.5, dash="dot"),
            annotation_text="FVG",
            annotation_font_color=border_color,
            annotation_font_size=8,
            row=1, col=1
        )

    # BOS / CHoCH markers
    for sp in smc.structure_points[-5:]:
        if sp.index < len(df):
            color = CHART_THEME["bull"] if sp.direction == "bullish" else CHART_THEME["bear"]
            symbol = "triangle-up" if sp.direction == "bullish" else "triangle-down"
            
            fig.add_trace(go.Scatter(
                x=[df.index[sp.index]],
                y=[sp.price],
                mode="markers+text",
                marker=dict(symbol=symbol, size=12, color=color),
                text=[sp.structure_type],
                textposition="top center",
                textfont=dict(color=color, size=9),
                name=sp.structure_type,
                showlegend=False
            ), row=1, col=1)


def _add_elliott_wave(fig: go.Figure, df: pd.DataFrame, ew: ElliottWaveResult):
    """Add Elliott Wave count lines to chart."""
    if not ew.wave_points:
        return
    
    valid_points = [wp for wp in ew.wave_points if wp.index < len(df)]
    if not valid_points:
        return

    x_coords = [df.index[wp.index] for wp in valid_points]
    y_coords = [wp.price for wp in valid_points]
    labels = [f"W{wp.wave_label}" for wp in valid_points]

    # Wave path lines
    fig.add_trace(go.Scatter(
        x=x_coords,
        y=y_coords,
        mode="lines+markers+text",
        line=dict(color=CHART_THEME["wave"], width=2, dash="dot"),
        marker=dict(size=10, color=CHART_THEME["wave"],
                    line=dict(color="#FFFFFF", width=1)),
        text=labels,
        textposition="top center",
        textfont=dict(color=CHART_THEME["wave"], size=11, family="JetBrains Mono"),
        name=f"EW: {ew.pattern_type}",
    ), row=1, col=1)

    # Projected target
    if ew.projected_target:
        last_x = x_coords[-1]
        fig.add_hline(
            y=ew.projected_target,
            line_dash="dot",
            line_color="#FFD700",
            line_width=1.5,
            annotation_text=f"  EW Target: {ew.projected_target:.5f}",
            annotation_font_color="#FFD700",
            row=1, col=1
        )


def _add_fibonacci_levels(fig: go.Figure, df: pd.DataFrame, ew: ElliottWaveResult):
    """Add Fibonacci retracement levels."""
    key_fibs = {"0.382": "#8B5CF6", "0.500": "#A78BFA", "0.618": "#7C3AED", "0.786": "#5B21B6"}
    
    for fib_key, color in key_fibs.items():
        level = ew.fib_levels.get(fib_key)
        if level:
            fig.add_hline(
                y=level,
                line_dash="dot",
                line_color=color,
                line_width=0.8,
                annotation_text=f"  Fib {fib_key}: {level:.5f}",
                annotation_font_color=color,
                annotation_font_size=9,
                row=1, col=1
            )


def create_pnl_chart(trade_history_df: pd.DataFrame) -> go.Figure:
    """Create cumulative P&L chart from trade history."""
    fig = go.Figure()
    
    if trade_history_df.empty or "pnl" not in trade_history_df.columns:
        fig.add_annotation(text="No trade history available", xref="paper", yref="paper",
                           x=0.5, y=0.5, showarrow=False, font=dict(color="white", size=14))
    else:
        df = trade_history_df.copy()
        df["pnl"] = pd.to_numeric(df["pnl"], errors="coerce").fillna(0)
        df["cumulative_pnl"] = df["pnl"].cumsum()
        
        colors = [CHART_THEME["bull"] if v >= 0 else CHART_THEME["bear"] for v in df["pnl"]]
        
        fig.add_trace(go.Bar(
            y=df["pnl"],
            name="Trade P&L",
            marker_color=colors,
        ))
        fig.add_trace(go.Scatter(
            y=df["cumulative_pnl"],
            name="Cumulative P&L",
            line=dict(color="#FFD700", width=2),
            mode="lines"
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_THEME["bg"],
        plot_bgcolor=CHART_THEME["bg"],
        font=dict(color=CHART_THEME["text"]),
        height=350,
        title="Performance History",
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig


def create_session_clock() -> go.Figure:
    """Create a visual Forex session activity chart."""
    sessions = {
        "Sydney":   {"start": 22, "end": 7, "color": "#4ECDC4"},
        "Tokyo":    {"start": 0,  "end": 9, "color": "#45B7D1"},
        "London":   {"start": 8,  "end": 17, "color": "#FFA07A"},
        "New York": {"start": 13, "end": 22, "color": "#98D8C8"},
    }

    from datetime import datetime
    import pytz
    now_utc = datetime.now(pytz.UTC).hour + datetime.now(pytz.UTC).minute / 60

    fig = go.Figure()

    for i, (name, info) in enumerate(sessions.items()):
        s, e = info["start"], info["end"]
        # Handle overnight
        if s > e:
            hours = list(range(s, 24)) + list(range(0, e))
        else:
            hours = list(range(s, e))
        
        fig.add_trace(go.Bar(
            x=[1] * len(hours),
            y=hours,
            orientation="v",
            name=name,
            marker_color=info["color"],
            opacity=0.7,
            base=0,
            width=0.8,
        ))

    fig.add_hline(y=now_utc, line_color="white", line_width=2, line_dash="dash",
                  annotation_text="Now (UTC)", annotation_font_color="white")

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=CHART_THEME["bg"],
        plot_bgcolor=CHART_THEME["bg"],
        height=300,
        title="Market Sessions (UTC)",
        barmode="overlay",
        font=dict(color=CHART_THEME["text"]),
        margin=dict(l=10, r=10, t=40, b=10),
    )
    return fig
