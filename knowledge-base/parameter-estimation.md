
# Weibull Parameter Estimation

To perform a Weibull analysis, you must first estimate the shape (β) and scale (η) parameters from a set of failure data. Common methods include Probability Plotting and Maximum Likelihood Estimation (MLE).

## Probability Plotting

This is a graphical method that is straightforward to implement.

1.  **Rank the failure times:** Order the failure times from smallest to largest.
2.  **Calculate the median rank:** A common formula for the median rank (MR) is Benard's approximation:
    MR = (i - 0.3) / (n + 0.4)
    Where `i` is the rank and `n` is the total number of failures.
3.  **Transform the data:** Take the natural logarithm of the failure times (`ln(t)`) and the double logarithm of the inverse of the unreliability (`ln(ln(1/(1-MR)))`).
4.  **Plot the data:** Plot the transformed values on a special type of graph paper (Weibull probability paper) or using software. The `ln(t)` values are on the x-axis and the `ln(ln(1/(1-MR)))` values are on the y-axis.
5.  **Fit a line:** Draw a best-fit straight line through the data points.

### Estimating Parameters from the Plot

- **Shape Parameter (β):** The slope of the fitted line is the estimate of β. 
  β = (y2 - y1) / (x2 - x1)

- **Scale Parameter (η):** The characteristic life, η, is the time corresponding to a cumulative failure probability of 63.2%. On the plot, this corresponds to a y-value of 0 (`ln(ln(1/(1-0.632))) = 0`). The value of η is the time `t` where the fitted line crosses the y=0 axis.
  η = exp(x-intercept)

## Maximum Likelihood Estimation (MLE)

MLE is a more robust statistical method that finds the parameter values that maximize the likelihood of observing the given set of failure data. This method is computationally intensive and usually requires specialized software. The likelihood function for the Weibull distribution is constructed, and numerical optimization techniques are used to find the values of β and η that maximize this function.
