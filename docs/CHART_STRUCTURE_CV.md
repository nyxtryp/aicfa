# AICFA Native Chart Structure CV

The first native Chart Vision stage is deterministic and CPU-only.

## Boundary

Input:
- user-supplied screenshot bytes.

Output:
- normalized pixel price trace;
- confirmed visual swing points;
- HH/HL/LH/LL labels where the image supports them.

This stage does not:
- recover exact market prices;
- infer a trade direction;
- emit BOS/CHoCH;
- detect FVG/OB/liquidity yet;
- execute orders;
- call an external model.

## Method

1. Decode the screenshot with OpenCV.
2. Restrict processing to the central chart price panel.
3. Segment saturated/high-value candle colors without assuming one exact RGB theme.
4. Build a per-column high/low pixel trace.
5. Interpolate small gaps and smooth the trace.
6. Detect local swing highs/lows with image-resolution-independent configuration.
7. Confirm swings only when subsequent visual movement exceeds a normalized pixel threshold.
8. Compare confirmed highs with prior highs to label HH/LH, and confirmed lows with prior lows to label HL/LL.

The output is intentionally an intermediate market-state representation. The existing VisualEvidence and Knowledge Base layers remain the semantic boundary for later SMC concepts.

## Performance requirement

The implementation is intended for CPU-only interactive use and must remain comfortably below the user's approximately 60-second ceiling.

## Current limitation

Candle segmentation is the first native heuristic and is expected to require calibration against multiple TradingView themes/layouts. Exact price recovery and SMC-specific structures are later stages.
