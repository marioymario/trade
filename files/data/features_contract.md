# Feature Contract (OHLCV → Features)

## Input schema (required)
`market_data` must be a pandas DataFrame with:

- timestamp: tz-aware UTC datetime64
- open, high, low, close: float
- volume: float

Rows must be sorted ascending by timestamp (the pipeline will sort defensively).

## Output schema (stable)
`compute_features()` returns a DataFrame with the following columns:

### Raw OHLCV
- timestamp
- open, high, low, close, volume

### Returns
- ret_1: percent return over 1 bar
- logret_1: log return over 1 bar

### Trend (EMA)
- ema_fast: EMA(close, 12)
- ema_slow: EMA(close, 26)
- ema_spread: (ema_fast - ema_slow) / ema_slow
- ema_slow_slope: ema_slow[t] - ema_slow[t-1]

### Volatility / risk
- atr: ATR(14) using EWMA smoothing
- atr_pct: atr / close

### Momentum
- rsi: RSI(14) using EWMA averages

### Volume
- vol_z: zscore(volume) rolling window 50
- dollar_vol: close * volume
- dollar_vol_z: zscore(dollar_vol) rolling window 50

## Safety rule
The system must NOT trade if the latest row contains NaNs.

Enforced by:
- `validate_latest_features(feats)` which raises if latest row has NaNs.

## Adding a new feature
Any new feature must include:
- name (column)
- definition (math + lookback)
- expected range (if known)
- failure modes / missingness behavior
- whether it can introduce lookahead bias

