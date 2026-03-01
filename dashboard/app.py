import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, "/work")

try:
    from files.data.features import compute_features  # type: ignore
except Exception as e:
    compute_features = None
    _import_err = e

st.set_page_config(page_title="Trade Dashboard", layout="wide")


def normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip()
    return sym.replace("/", "_")


def _read_text(p: Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(errors="replace")


def parse_kv_text(txt: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (txt or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _find_latest_partitions(raw_root: Path, days: int) -> list[Path]:
    parts = sorted(raw_root.glob("date=*/bars.parquet"))
    if not parts:
        return []
    cutoff = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    keep: list[Path] = []
    for p in parts:
        try:
            d = p.parent.name.split("date=")[1]
            dd = datetime.strptime(d, "%Y-%m-%d").date()
            if dd >= cutoff:
                keep.append(p)
        except Exception:
            continue
    return keep if keep else parts[-min(len(parts), days):]


@st.cache_data(ttl=10)
def load_bars(parquet_paths: tuple[str, ...], max_rows: int) -> pd.DataFrame:
    dfs = []
    for s in parquet_paths:
        try:
            dfs.append(pd.read_parquet(s))
        except Exception:
            continue
    if not dfs:
        return pd.DataFrame()

    df = pd.concat(dfs, ignore_index=True)

    if "timestamp" not in df.columns:
        for alt in ("ts", "time", "datetime", "ts_utc", "ts_ms"):
            if alt in df.columns:
                df = df.rename(columns={alt: "timestamp"})
                break
    if "timestamp" not in df.columns:
        return pd.DataFrame()

    ts = df["timestamp"]
    if pd.api.types.is_integer_dtype(ts) or pd.api.types.is_float_dtype(ts):
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    else:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")

    cols = [c for c in ["timestamp", "open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[cols].dropna(subset=["timestamp"]).sort_values("timestamp")

    if max_rows and len(df) > max_rows:
        df = df.iloc[-max_rows:]
    return df.reset_index(drop=True)


@st.cache_data(ttl=10)
def load_csv(path: str, max_rows: int) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    try:
        df = pd.read_csv(p)
    except Exception:
        return pd.DataFrame()
    if max_rows and len(df) > max_rows:
        df = df.iloc[-max_rows:]
    return df


def ts_from_ms(v):
    if v is None:
        return pd.NaT
    try:
        if isinstance(v, float) and pd.isna(v):
            return pd.NaT
        return pd.to_datetime(int(v), unit="ms", utc=True)
    except Exception:
        return pd.NaT


def pill(label: str, value: str, tone: str) -> str:
    cls = {
        "good": "pill pill-good",
        "warn": "pill pill-warn",
        "bad": "pill pill-bad",
        "info": "pill pill-info",
    }.get(tone, "pill pill-info")
    return f'<span class="{cls}"><b>{label}</b>: {value}</span>'


def build_event_tables(
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    trades: pd.DataFrame,
    show_entries: bool,
    show_exits: bool,
    show_decisions: bool,
    show_stops: bool,
):
    bar_min = bars["timestamp"].min() if not bars.empty else None
    bar_max = bars["timestamp"].max() if not bars.empty else None

    def in_window(ts):
        if bar_min is None or bar_max is None:
            return True
        return ts >= bar_min and ts <= bar_max

    entries = []
    exits = []
    decs = []
    stops = []

    if trades is not None and not trades.empty:
        for _, r in trades.tail(2000).iterrows():
            side = str(r.get("side", "")).strip()
            ep = r.get("entry_price")
            et = r.get("entry_ts_ms")
            xp = r.get("exit_price")
            xt = r.get("exit_ts_ms")
            xr = str(r.get("exit_reason", "")).strip()
            pnl = r.get("realized_pnl_usd")
            pnl_pct = r.get("realized_pnl_pct")

            if show_entries:
                ts = ts_from_ms(et)
                if pd.notna(ts) and in_window(ts) and ep is not None and not (isinstance(ep, float) and pd.isna(ep)):
                    price = float(ep)
                    hover = f"TRADE ENTRY<br>side={side}<br>price={price:.2f}<br>ts={ts}"
                    entries.append({"timestamp": ts, "price": price, "label": f"ENTRY {side}", "hover": hover})

            if show_exits:
                ts = ts_from_ms(xt)
                if pd.notna(ts) and in_window(ts) and xp is not None and not (isinstance(xp, float) and pd.isna(xp)):
                    price = float(xp)
                    hover = f"TRADE EXIT<br>reason={xr}<br>price={price:.2f}"
                    if pnl is not None and not (isinstance(pnl, float) and pd.isna(pnl)):
                        hover += f"<br>pnl_usd={float(pnl):.4f}"
                    if pnl_pct is not None and not (isinstance(pnl_pct, float) and pd.isna(pnl_pct)):
                        hover += f"<br>pnl_pct={float(pnl_pct):.4%}"
                    hover += f"<br>ts={ts}"
                    exits.append({"timestamp": ts, "price": price, "label": f"EXIT {xr}", "hover": hover})

    if decisions is not None and not decisions.empty:
        for _, r in decisions.tail(2500).iterrows():
            ts = ts_from_ms(r.get("ts_ms"))
            if pd.isna(ts) or not in_window(ts):
                continue

            if show_decisions and bool(r.get("entry_should_enter")):
                side = str(r.get("entry_side", "")).strip() or "ENTRY"
                reason = str(r.get("entry_reason", "")).strip()
                price = r.get("position_entry_price")
                if price is not None and not (isinstance(price, float) and pd.isna(price)):
                    pr = float(price)
                    decs.append(
                        {
                            "timestamp": ts,
                            "price": pr,
                            "label": f"D-ENTRY {side}",
                            "hover": f"DECISION ENTRY<br>side={side}<br>price={pr:.2f}<br>reason={reason}<br>ts={ts}",
                        }
                    )

            if show_decisions and bool(r.get("exit_should_exit")):
                reason = str(r.get("exit_reason", "")).strip()
                price = r.get("position_stop_price")
                if price is not None and not (isinstance(price, float) and pd.isna(price)):
                    pr = float(price)
                    decs.append(
                        {
                            "timestamp": ts,
                            "price": pr,
                            "label": "D-EXIT",
                            "hover": f"DECISION EXIT<br>stop_price={pr:.2f}<br>reason={reason}<br>ts={ts}",
                        }
                    )

            if show_stops:
                sp = r.get("position_stop_price")
                if sp is not None and not (isinstance(sp, float) and pd.isna(sp)):
                    pr = float(sp)
                    pos_side = str(r.get("position_side", "")).strip()
                    hover = f"STOP LEVEL<br>side={pos_side}<br>stop={pr:.2f}<br>ts={ts}"
                    stops.append({"timestamp": ts, "price": pr, "label": "STOP", "hover": hover})

    entries_df = pd.DataFrame(entries, columns=["timestamp", "price", "label", "hover"])
    exits_df = pd.DataFrame(exits, columns=["timestamp", "price", "label", "hover"])
    decs_df = pd.DataFrame(decs, columns=["timestamp", "price", "label", "hover"])
    stops_df = pd.DataFrame(stops, columns=["timestamp", "price", "label", "hover"])

    for df in (entries_df, exits_df, decs_df, stops_df):
        if not df.empty:
            df.dropna(subset=["timestamp", "price"], inplace=True)
            df.sort_values("timestamp", inplace=True)

    return entries_df, exits_df, decs_df, stops_df


def candle_figure(df: pd.DataFrame, feats: pd.DataFrame | None, entries, exits, decs, stops) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Candlestick(
            x=df["timestamp"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLC",
            showlegend=False,
        )
    )

    if feats is not None and not feats.empty:
        if "ema_fast" in feats.columns:
            fig.add_trace(go.Scatter(x=feats["timestamp"], y=feats["ema_fast"], mode="lines", name="ema_fast"))
        if "ema_slow" in feats.columns:
            fig.add_trace(go.Scatter(x=feats["timestamp"], y=feats["ema_slow"], mode="lines", name="ema_slow"))

    if entries is not None and not entries.empty:
        fig.add_trace(
            go.Scatter(
                x=entries["timestamp"],
                y=entries["price"],
                mode="markers",
                name="entries",
                marker=dict(symbol="triangle-up", size=11),
                hovertext=entries["hover"],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )

    if exits is not None and not exits.empty:
        fig.add_trace(
            go.Scatter(
                x=exits["timestamp"],
                y=exits["price"],
                mode="markers",
                name="exits",
                marker=dict(symbol="triangle-down", size=11),
                hovertext=exits["hover"],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )

    if decs is not None and not decs.empty:
        fig.add_trace(
            go.Scatter(
                x=decs["timestamp"],
                y=decs["price"],
                mode="markers",
                name="decision signals",
                marker=dict(symbol="circle", size=7),
                hovertext=decs["hover"],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )

    if stops is not None and not stops.empty:
        fig.add_trace(
            go.Scatter(
                x=stops["timestamp"],
                y=stops["price"],
                mode="markers",
                name="stops",
                marker=dict(symbol="x", size=6),
                hovertext=stops["hover"],
                hovertemplate="%{hovertext}<extra></extra>",
            )
        )

    x0 = df["timestamp"].iloc[0]
    x1 = df["timestamp"].iloc[-1]
    fig.update_xaxes(range=[x0, x1])
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, margin=dict(l=10, r=10, t=30, b=10))
    return fig


def indicator_figure(feats: pd.DataFrame, x0, x1, kind: str) -> go.Figure:
    fig = go.Figure()
    if kind == "rsi":
        fig.add_trace(go.Scatter(x=feats["timestamp"], y=feats["rsi"], mode="lines", name="rsi"))
        fig.add_hline(y=70, line_dash="dash")
        fig.add_hline(y=30, line_dash="dash")
        fig.update_yaxes(range=[0, 100])
        fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10))
    elif kind == "atr":
        fig.add_trace(go.Scatter(x=feats["timestamp"], y=feats["atr_pct"], mode="lines", name="atr_pct"))
        fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10))
    fig.update_xaxes(range=[x0, x1])
    return fig


def pnl_strip(trades_window: pd.DataFrame) -> dict:
    if trades_window.empty:
        return {
            "trades": 0,
            "pnl_usd": 0.0,
            "pnl_pct_mean": 0.0,
            "wins": 0,
            "win_rate": 0.0,
            "stop_hit": 0,
            "other_exits": 0,
            "avg_pnl": 0.0,
            "median_pnl": 0.0,
        }
    pnl = trades_window.get("realized_pnl_usd")
    pnl_pct = trades_window.get("realized_pnl_pct")
    pnl_usd_sum = float(pd.to_numeric(pnl, errors="coerce").fillna(0.0).sum()) if pnl is not None else 0.0
    pnl_pct_mean = float(pd.to_numeric(pnl_pct, errors="coerce").dropna().mean()) if pnl_pct is not None else 0.0

    pnl_num = pd.to_numeric(trades_window.get("realized_pnl_usd"), errors="coerce")
    wins = int((pnl_num > 0).sum()) if pnl_num is not None else 0
    trades_n = int(len(trades_window))
    win_rate = float(wins / trades_n) if trades_n else 0.0

    exit_reason = trades_window.get("exit_reason")
    stop_hit = int((exit_reason == "stop_hit").sum()) if exit_reason is not None else 0
    other_exits = trades_n - stop_hit

    avg_pnl = float(pnl_num.dropna().mean()) if pnl_num is not None and pnl_num.notna().any() else 0.0
    median_pnl = float(pnl_num.dropna().median()) if pnl_num is not None and pnl_num.notna().any() else 0.0

    return {
        "trades": trades_n,
        "pnl_usd": pnl_usd_sum,
        "pnl_pct_mean": pnl_pct_mean,
        "wins": wins,
        "win_rate": win_rate,
        "stop_hit": stop_hit,
        "other_exits": other_exits,
        "avg_pnl": avg_pnl,
        "median_pnl": median_pnl,
    }


st.markdown(
    """
<style>
.pill {display:inline-block; padding:6px 10px; border-radius:999px; margin-right:8px; margin-bottom:8px; font-size:14px;}
.pill-good {background:#0f2f1d; color:#b9f6c0; border:1px solid #1a7f37;}
.pill-warn {background:#2f2a0f; color:#ffe08a; border:1px solid #b08900;}
.pill-bad  {background:#2f0f0f; color:#ffb3b3; border:1px solid #b42318;}
.pill-info {background:#0f1f2f; color:#b3d7ff; border:1px solid #175cd3;}
.block {padding:12px 14px; border-radius:14px; border:1px solid rgba(255,255,255,0.08);}
.small {opacity:0.8; font-size:13px;}
</style>
""",
    unsafe_allow_html=True,
)

st.title("Trade Dashboard (Charts + Ops)")

flags_dir = os.environ.get("FLAGS_DIR") or str(Path.home() / "trade_flags")
status_path = Path(flags_dir) / "status.txt"
status_txt = _read_text(status_path)
status_kv = parse_kv_text(status_txt)

with st.sidebar:
    st.subheader("Session")
    data_tag = st.text_input("DATA_TAG", value=os.environ.get("DATA_TAG", "paper_oldbox_live"))
    symbol_raw = st.text_input("SYMBOL", value=os.environ.get("SYMBOL", "BTC_USD"))
    symbol = normalize_symbol(symbol_raw)
    if symbol != symbol_raw:
        st.caption(f"Normalized SYMBOL → {symbol}")

    timeframe = st.text_input("TIMEFRAME", value=os.environ.get("TIMEFRAME", "5m"))
    days = st.slider("Lookback days", 1, 14, 3)
    max_rows = st.slider("Max bars", 200, 5000, 1500, step=100)

    st.subheader("Overlays / Events")
    show_entries = st.checkbox("Show Trade Entries", value=True)
    show_exits = st.checkbox("Show Trade Exits", value=True)
    show_decisions = st.checkbox("Show Decision Signals (D-ENTRY/D-EXIT)", value=False)
    show_stops = st.checkbox("Show Stop Levels (position_stop_price)", value=True)

    st.subheader("Indicators")
    show_rsi = st.checkbox("Show RSI", value=True)
    show_atr = st.checkbox("Show ATR%", value=True)

    st.subheader("PnL window")
    pnl_window_mode = st.radio("Window mode", ["exit_ts in window", "entry_ts in window"], index=0)

    st.caption(f"FLAGS_DIR: {flags_dir}")

raw_root = Path("data/raw") / data_tag / symbol / timeframe
decisions_csv = Path("data/processed/decisions") / data_tag / symbol / timeframe / "decisions.csv"
trades_csv = Path("data/processed/trades") / data_tag / symbol / timeframe / "trades.csv"

decisions = load_csv(str(decisions_csv), max_rows=200000)
trades = load_csv(str(trades_csv), max_rows=200000)

latest_dec = None
if not decisions.empty:
    latest_dec = decisions.sort_values("ts_ms").tail(1).iloc[0] if "ts_ms" in decisions.columns else decisions.tail(1).iloc[0]

trend = str(latest_dec.get("trend")) if latest_dec is not None and "trend" in latest_dec else "na"
volatility = str(latest_dec.get("volatility")) if latest_dec is not None and "volatility" in latest_dec else "na"
market_reason = str(latest_dec.get("market_reason")) if latest_dec is not None and "market_reason" in latest_dec else ""
last_dec_ts = str(latest_dec.get("timestamp")) if latest_dec is not None and "timestamp" in latest_dec else "na"
pos_side = str(latest_dec.get("position_side")) if latest_dec is not None and "position_side" in latest_dec else "na"

last_trade = trades.tail(1).iloc[0] if not trades.empty else None
last_exit_reason = str(last_trade.get("exit_reason")) if last_trade is not None and "exit_reason" in last_trade else "na"
last_pnl = last_trade.get("realized_pnl_usd") if last_trade is not None and "realized_pnl_usd" in last_trade else None

STOP = status_kv.get("STOP", "na")
HALT = status_kv.get("HALT", "na")
ARM = status_kv.get("ARM", "na")
paper_status = status_kv.get("paper_status", "na")
trade_status = status_kv.get("trade_status", "na")
dashboard_status = status_kv.get("dashboard_status", "na")
beacon_ts = status_kv.get("ts_utc", "na")
dec_mtime = status_kv.get("decisions_mtime_utc", "na")


def tone_on_off(v: str) -> str:
    v = (v or "").strip().upper()
    if v == "ON":
        return "bad"
    if v == "OFF":
        return "good"
    return "info"


def tone_up_down(v: str) -> str:
    v = (v or "").strip().lower()
    if v == "up":
        return "good"
    if v == "down":
        return "bad"
    return "info"


def tone_trend(v: str) -> str:
    v = (v or "").strip().lower()
    if v in ("up", "bull", "bullish"):
        return "good"
    if v in ("down", "bear", "bearish"):
        return "bad"
    return "warn"


with st.container():
    c1, c2 = st.columns([1, 1])

    with c1:
        st.markdown("<div class='block'>", unsafe_allow_html=True)
        st.markdown("### Safety", unsafe_allow_html=True)
        st.markdown(
            " ".join(
                [
                    pill("STOP", STOP, tone_on_off(STOP)),
                    pill("HALT", HALT, tone_on_off(HALT)),
                    pill("ARM", ARM, "good" if (ARM or "").upper() == "ON" else "warn"),
                ]
            ),
            unsafe_allow_html=True,
        )
        st.markdown(
            " ".join(
                [
                    pill("paper", paper_status, tone_up_down(paper_status)),
                    pill("trade", trade_status, tone_up_down(trade_status)),
                    pill("dashboard", dashboard_status, tone_up_down(dashboard_status)),
                ]
            ),
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='small'>beacon_ts={beacon_ts} · decisions_mtime_utc={dec_mtime}</div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("<div class='block'>", unsafe_allow_html=True)
        st.markdown("### Regime (latest decision)", unsafe_allow_html=True)
        st.markdown(
            " ".join(
                [
                    pill("trend", trend, tone_trend(trend)),
                    pill("volatility", volatility, "warn" if (volatility or "").lower() != "normal" else "good"),
                    pill("position", pos_side, "info"),
                ]
            ),
            unsafe_allow_html=True,
        )
        if market_reason:
            st.markdown(f"<div class='small'>market_reason: {market_reason}</div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='small'>last_decision_ts={last_dec_ts} · last_trade_exit={last_exit_reason}"
            + (f" · last_pnl_usd={float(last_pnl):.4f}" if last_pnl is not None and not pd.isna(last_pnl) else "")
            + "</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

colA, colB = st.columns([1, 1])
with colA:
    st.subheader("Beacon (raw)")
    if status_txt:
        st.code(status_txt, language="text")
    else:
        st.warning("No status.txt found yet.")
with colB:
    st.subheader("Feature pipeline")
    if compute_features is None:
        st.error(f"Could not import compute_features: {_import_err}")
    else:
        st.success("compute_features() import OK")

st.subheader("Market chart")

parquets = _find_latest_partitions(raw_root, days=days)
st.caption(f"raw_root: {raw_root}")
st.caption(f"parquet parts found: {len(parquets)}")
if not parquets:
    st.error(f"No parquet bars found under: {raw_root}")
    st.stop()

bars = load_bars(tuple(str(p) for p in parquets), max_rows=max_rows)
st.caption(f"Loaded bars: {len(bars)}")
if bars.empty:
    st.error("Loaded 0 bars (schema mismatch or read error).")
    st.write("Tried paths:", [str(p) for p in parquets])
    st.stop()

feats = None
if compute_features is not None:
    try:
        feats = compute_features(bars.copy())
    except Exception as e:
        st.warning(f"compute_features() failed: {e}")

entries, exits, dec_events, stop_events = build_event_tables(
    bars, decisions, trades,
    show_entries=show_entries,
    show_exits=show_exits,
    show_decisions=show_decisions,
    show_stops=show_stops,
)

fig = candle_figure(bars, feats, entries, exits, dec_events, stop_events)
st.plotly_chart(fig, use_container_width=True)

# --- Indicators panels ---
if feats is not None and not feats.empty:
    x0 = bars["timestamp"].iloc[0]
    x1 = bars["timestamp"].iloc[-1]

    if show_rsi and "rsi" in feats.columns:
        st.subheader("RSI (14)")
        st.plotly_chart(indicator_figure(feats, x0, x1, "rsi"), use_container_width=True)

    if show_atr and "atr_pct" in feats.columns:
        st.subheader("ATR% (14)")
        st.plotly_chart(indicator_figure(feats, x0, x1, "atr"), use_container_width=True)

# --- PnL strip + window-synced trades ---
st.subheader("PnL (window-synced)")

if not trades.empty:
    bar_min = bars["timestamp"].min()
    bar_max = bars["timestamp"].max()

    tw = trades.copy()
    tw["entry_ts"] = tw["entry_ts_ms"].apply(ts_from_ms) if "entry_ts_ms" in tw.columns else pd.NaT
    tw["exit_ts"] = tw["exit_ts_ms"].apply(ts_from_ms) if "exit_ts_ms" in tw.columns else pd.NaT

    if pnl_window_mode == "entry_ts in window":
        tw = tw[(tw["entry_ts"].notna()) & (tw["entry_ts"] >= bar_min) & (tw["entry_ts"] <= bar_max)]
    else:
        tw = tw[(tw["exit_ts"].notna()) & (tw["exit_ts"] >= bar_min) & (tw["exit_ts"] <= bar_max)]

    stats = pnl_strip(tw)

    # Display strip
    s1, s2, s3, s4, s5 = st.columns([1, 1, 1, 1, 1])
    s1.metric("Trades", f"{stats['trades']}")
    s2.metric("Realized PnL (USD)", f"{stats['pnl_usd']:.4f}")
    s3.metric("Mean PnL% (per trade)", f"{stats['pnl_pct_mean']:.3%}")
    s4.metric("Win rate", f"{stats['win_rate']:.1%}")
    s5.metric("stop_hit / other", f"{stats['stop_hit']} / {stats['other_exits']}")

    s6, s7 = st.columns([1, 1])
    s6.metric("Avg pnl/trade (USD)", f"{stats['avg_pnl']:.4f}")
    s7.metric("Median pnl/trade (USD)", f"{stats['median_pnl']:.4f}")

    st.caption(f"Trades filtered by: {pnl_window_mode} ∈ [{bar_min}, {bar_max}]")

    show_cols = [
        "exchange", "symbol", "timeframe", "side",
        "entry_ts_ms", "exit_ts_ms",
        "entry_price", "exit_price", "exit_reason",
        "realized_pnl_usd", "realized_pnl_pct",
        "stop_price", "market_reason",
    ]
    present_cols = [c for c in show_cols if c in tw.columns]
    tw_show = tw[present_cols].tail(200).copy()
    st.dataframe(tw_show, use_container_width=True)
else:
    st.info("No trades.csv loaded yet for this session.")

st.subheader("Recent decisions / trades (raw tails)")
c1, c2 = st.columns([1, 1])
with c1:
    st.caption(str(decisions_csv))
    st.dataframe(decisions.tail(50), use_container_width=True)
with c2:
    st.caption(str(trades_csv))
    st.dataframe(trades.tail(50), use_container_width=True)
