
# Weibull Analysis Basics

The Weibull distribution is a versatile continuous probability distribution used in reliability engineering to model failure times. It can mimic the behavior of other statistical distributions such as the normal and exponential distributions.

## Key Characteristics

- **Shape Parameter (β - Beta):** Also known as the slope, this parameter determines the shape of the distribution and the nature of the failure rate.
  - **β < 1:** The failure rate decreases over time (infant mortality). Early failures are likely.
  - **β = 1:** The failure rate is constant over time. This simplifies to the exponential distribution, indicating random failures.
  - **β > 1:** The failure rate increases over time (wear-out failures). Failures become more likely as the component ages.

- **Scale Parameter (η - Eta):** Also known as the characteristic life, this is the time at which 63.2% of the population is expected to have failed. It stretches or compresses the distribution along the time axis.

- **Location Parameter (γ - Gamma):** Also known as the failure-free life, this represents a period of time where no failures are expected to occur. For many analyses, this is assumed to be zero.

## Probability Density Function (PDF)

The PDF for the two-parameter Weibull distribution is:

f(t) = (β/η) * (t/η)^(β-1) * exp(-(t/η)^β)

Where:
- `t` is the time
- `β` is the shape parameter
- `η` is the scale parameter
