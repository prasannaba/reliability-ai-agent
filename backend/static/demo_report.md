# Reliability analysis report

Computed by MCP tools (Weibull fit, B-life). The language model does not invent life metrics.

## Question

Does B10 cover a 200-hour warranty on this sample?

## Sample

- Failures: 8
- Suspensions (right-censored): 3
- Fit method: median ranks + RRY

## Estimates

- Shape β: 1.538
- Scale η: 643.85 hours
- MTBF: 579.54 hours
- B10: 149.1 hours
- B20: 242.9 hours
- B30: 329.4 hours

## 90% bootstrap percentile bounds

- Method: bootstrap percentile
- β: 1.186 – 2.247
- η (hours): 456.16 – 831.41
- B10 (hours): 94.2 – 252.4
- B20 (hours): 169.5 – 369.9

## Warranty check

B10 is 149.1 h versus a 200 h warranty — B10 **does not cover** the warranty period on the point estimate.

## Plot

![Weibull paper](weibull_plot_1787390934358.png)

## Knowledge-base citations

- `weibull_basics.md`: Probability Density Function (PDF)

## Notes

- This copilot complements commercial solvers (e.g. ReliaSoft Weibull++) via MCP later; it is not a replacement for ALT, Weibayes, or competing-risks analysis.
- Informal K-S on failures: statistic=0.2734071728593175, p=0.5043595033331769.