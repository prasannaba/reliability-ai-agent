import argparse
import sys
import time
import warnings

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from scipy import stats
from scipy.special import gamma

warnings.filterwarnings("ignore")


def weibull_cdf(t, beta, eta):
    """Weibull CDF: F(t) = 1 - exp(-(t/eta)^beta)"""
    return 1 - np.exp(-((t / eta) ** beta))


def linearize_weibull(t, F):
    """
    Linearize Weibull CDF for plotting on Weibull paper
    From: F(t) = 1 - exp(-(t/eta)^beta)

    Step 1: Rearrange
    1 - F(t) = exp(-(t/eta)^beta)

    Step 2: Take natural log of both sides
    ln(1 - F(t)) = -(t/eta)^beta

    Step 3: Multiply by -1 and take ln again
    ln(-ln(1 - F(t))) = ln((t/eta)^beta)
    ln(ln(1/(1-F))) = beta*ln(t) - beta*ln(eta)

    This gives us the linear form:
    y = beta*x - beta*ln(eta)
    where y = ln(ln(1/(1-F))) and x = ln(t)

    This is in the form y = mx + c where:
    m = beta (slope)
    c = -beta*ln(eta) (intercept)
    """
    # Avoid F = 0 or F = 1
    F = np.clip(F, 1e-10, 1 - 1e-10)
    y = np.log(np.log(1 / (1 - F)))
    x = np.log(t)  # Natural log for x-axis
    return x, y


def estimate_weibull_params(
    failure_times,
):  # -> tuple[Any, Any, NDArray, NDArray[floating[Any]], Any, Any]:
    """
    Estimate Weibull parameters using median rank method and linear regression.

    Returns beta (shape), eta (scale), and intermediate calculation values.
    """
    # Sort failure times
    t_sorted = np.sort(failure_times)
    n = len(t_sorted)

    # Calculate median ranks (approximation for CDF)
    ranks = np.arange(1, n + 1)
    F = (ranks - 0.3) / (n + 0.4)  # Bernard's median rank approximation

    # Linearize: y = ln(ln(1/(1-F))), x = ln(t)
    x, y = linearize_weibull(t_sorted, F)

    # Linear regression: y = m*x + c
    # where m = beta and c = -beta*ln(eta)
    m, c = np.polyfit(x, y, 1)

    # Extract Weibull parameters
    beta = m  # slope is directly beta
    eta = np.exp(-c / beta)

    return beta, eta, t_sorted, F, x, y


def calculate_b_life(beta, eta, percentage):
    """
    Calculates the B-Life for a given percentage.

    Args:
        beta (float): The Weibull shape parameter.
        eta (float): The Weibull scale parameter.
        percentage (float): The percentage for the B-Life calculation (e.g., 10 for B10).

    Returns:
        float: The calculated B-Life.
    """
    F_t = percentage / 100.0
    b_life = eta * (-np.log(1 - F_t))**(1 / beta)
    b_life = np.round(b_life).astype(int)
    return b_life


def create_weibull_paper(ax, title):
    """Create Weibull probability paper grid"""
    # Probability values for horizontal grid lines
    prob_values = [1, 2, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 98, 99, 99.9]
    prob_positions = [np.log(np.log(1 / (1 - p / 100))) for p in prob_values]

    # Add horizontal grid lines
    for pos, prob in zip(prob_positions, prob_values):
        ax.axhline(y=pos, color="gray", linestyle="-", alpha=0.3, linewidth=0.5)

    # Formatting of axes
    ax.set_title(title, fontsize=12, fontweight="bold", pad=5)
    ax.grid(True, which="both", ls="--")
    ax.set_yticks(prob_positions)
    ax.set_yticklabels([f"{p}%" for p in prob_values])
    ax.set_ylabel("Cumulative Probability (%)", fontsize=10)
    ax.set_xscale("log")
    ax.set_xlabel("ln(Time to Failure in Hours)", fontsize=10)

    return prob_positions


def plot_weibull_analysis(failure_times, title="Weibull Probability Plot"):
    """Main function to create Weibull analysis plot"""
    # Estimate parameters
    beta, eta, t_sorted, F, x_data, y_data = estimate_weibull_params(failure_times)

    # Check the default
    # print(f"Default figsize: {plt.rcParams['figure.figsize']} inches")
    # matplotlib default figsize: [6.4, 4.8] inches

    plt.rcParams["font.family"] = "Arial"

    fig = plt.figure(figsize=(8.5, 11))
    # Define a 2x2 grid with specific ratios:
    # width_ratios=[2, 1] means column 0 is twice as wide as column 1.
    # height_ratios=[2, 1] means row 0 is twice as tall as row 1.
    gs = GridSpec(
        nrows=2,
        ncols=2,
        figure=fig,
        width_ratios=[1, 1],
        height_ratios=[3, 1],
        top=0.91,
        bottom=0.11,
        left=0.11,
        right=0.91,
        hspace=0.3,
        wspace=0.3,
    )
    ax1 = fig.add_subplot(gs[0, :])
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    # Create Weibull paper
    prob_positions = create_weibull_paper(ax1, title)

    # Plot data points
    ax1.plot(
        t_sorted,
        y_data,
        "o",
        markersize=8,
        color="blue",
        label="Failure Data",
        markerfacecolor="lightblue",
        markeredgewidth=2,
        markeredgecolor="blue",
    )

    # Plot fitted line
    cdf_values = np.linspace(0.001, 0.999, 100)
    y_fit = [np.log(-np.log(1 - cdf)) for cdf in cdf_values]
    x_fit = np.exp((np.array(y_fit) / beta + np.log(eta)))

    ax1.plot(
        x_fit, y_fit, color="black", linestyle="-", linewidth=2.0, label="Fitted Line"
    )

    # Highlight 63.2% probability (scale parameter)
    F_632 = 0.632
    y_632 = np.log(np.log(1 / (1 - F_632)))
    x_632 = eta

    # Draw horizontal and vertical lines to eta at 63.2%
    ax1.axhline(y=y_632, color="green", linestyle="--", linewidth=2, alpha=0.7)
    ax1.axvline(x=x_632, color="green", linestyle="--", linewidth=2, alpha=0.7)
    ax1.plot(
        x_632,
        y_632,
        "s",
        markersize=12,
        color="green",
        markeredgewidth=2,
        markeredgecolor="darkgreen",
        label=f"η (Scale) = {eta:.2f} at 63.2%",
    )

    # Beta reference line: parallel to fitted line, starts at (0, 63.2%)
    # This is the traditional Weibull paper method where you draw a line parallel
    # to the fitted line starting from x=0 at 63.2% probability level
    # The point where this line intersects the top edge gives the beta value

    y_max = max(prob_positions) + 0.5
    y_min = min(prob_positions) - 0.5
    ax1.set_ylim([y_min, y_max])

    # Get x limits
    x_min, x_max = ax1.get_xlim()

    # Beta reference line starts at x=0 and y=63.2%
    # Line equation: y - y_632 = beta * (x - 0)
    # y = beta * x + y_632

    x_beta_start = 0  # Start from x = 0
    y_beta_start = y_632  # Start from 63.2%

    # Calculate where this line intersects the top edge
    # y_max = beta * x_top + y_632
    x_top = (y_max - y_632) / beta

    # Draw the beta reference line (parallel to fitted line, from (0, 63.2%))
    x_beta_range = np.array([x_beta_start, x_top])
    y_beta_range = np.array([y_beta_start, y_max])

    ax1.plot(
        np.exp(x_beta_range),
        y_beta_range,
        "purple",
        linewidth=2.5,
        linestyle="-.",
        label=f"β Line (from (0, 63.2%)) = {beta:.3f}",
    )

    # Add scale values on top axis for beta reference
    ax1_1 = ax1.twiny()
    beta_values = [0.5, 1, 2, 3, 4, 5, 8, 10]
    ax1_1.set_xlim(np.log(ax1.get_xlim()))
    ax1_1.set_xlabel(
        "Shape Parameter (β) Reference", fontsize=10, fontweight="bold", color="purple"
    )
    ax1_1.set_xscale("linear")

    # For each beta value, calculate where a line with that slope starting from
    # (0, y_632) would intersect the top edge
    beta_positions = []
    for b in beta_values:
        x_intersect = (y_max - y_632) / b
        beta_positions.append(x_intersect)

    ax1_1.set_xticks(beta_positions)
    ax1_1.set_xticklabels([f"{b}" for b in beta_values], color="purple", fontsize=8)

    # Mark the calculated beta value on the top axis
    ax1_1.plot(
        x_top,
        y_max,
        "v",
        markersize=10,
        color="purple",
        markeredgewidth=2,
        markeredgecolor="darkviolet",
        clip_on=False,
        zorder=10,
    )

    # Add statistics box
    # MTBF=η⋅Γ(1+1/β​)
    mtbf = eta * gamma(1 + 1 / (1 if abs(beta - 1) < 0.1 else beta))
    stats_text = "Weibull Parameters:\n"
    stats_text += f"Shape (β): {beta:.3f}\n"
    stats_text += f"Scale (η): {eta:.2f} hours\n"
    stats_text += f"MTBF: {mtbf:.2f} hours\n"
    stats_text += f"n = {len(failure_times)} failures"

    ax1.text(
        0.02,
        0.98,
        stats_text,
        transform=ax1.transAxes,
        fontsize=10,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8),
    )

    # Perform Kolmogorov-Smirnov test
    ks_stat, p_value = stats.kstest(
        failure_times, lambda x: stats.weibull_min.cdf(x, beta, scale=eta)
    )

    # Add goodness of fit text
    fit_text = "Goodness of Fit:\n"
    fit_text += f"K-S Statistic: {ks_stat:.4f}\n"
    fit_text += f"p-value: {p_value:.4f}\n"
    if p_value > 0.05:
        fit_text += "Good fit ✓"
    else:
        fit_text += "Poor fit ✗"

    ax1.text(
        0.98,
        0.2,
        fit_text,
        transform=ax1.transAxes,
        fontsize=9,
        verticalalignment="bottom",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8),
    )

    ax1.legend(loc="lower right", fontsize=10, framealpha=0.9)

    ax2.hist(failure_times, bins=8, color="blue", edgecolor="white", label="Samples")
    ax2.set_title("Histogram", fontsize=12, fontweight="bold", pad=5)
    ax2.set_xlabel("Time in Hours")
    ax2.set_ylabel("Frequency of Failure")
    ax2.legend()

    # Hazard Rate
    beta = 1 if abs(beta - 1) < 0.1 else beta
    hazard_function = stats.weibull_min.pdf(
        t_sorted, c=beta, scale=eta
    ) / stats.weibull_min.sf(t_sorted, c=beta, scale=eta)
    ax3.plot(t_sorted, hazard_function, color="black", linewidth=1.5)
    ax3.set_title("Hazard Rate (Trend)", fontsize=12, fontweight="bold", pad=5)
    ax3.set_xlabel("Time in Hours")
    ax3.set_ylabel("Hazard Function")

    plt.tight_layout()

    script_dir = Path(__file__).parent
    # Define the static directory at the root level (e.g., /backend/static)
    static_dir = script_dir / "static"

    # Now, use the new variable in your setup:
    if not static_dir.exists():
        static_dir.mkdir()

    time_suffix = int(time.time() * 1000)
    save_path = str(static_dir / f"weibull_plot_{time_suffix}.png")
    fig.savefig(save_path, dpi=300, bbox_inches="tight")

    return {
        "file": save_path,
        "beta": beta,
        "eta": eta,
        "mtbf": mtbf,
        "ks_stat": ks_stat,
        "p_value": p_value,
        "message": f"Weibull plot saved as {save_path}"
    }
    # return fig, beta, eta, mtbf, ks_stat, p_value


# Example usage
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Weibull Distribution Analysis")
    parser.add_argument(
        "--failure_data",
        type=int,
        nargs="+",
        default=None,
        required=False,
        help="Failure times (space-separated values)",
    )
    parser.add_argument(
        "--good_fit",
        type=bool,
        default=False,
        required=False,
        help="Goodness of fit (default: False)",
    )
    # add options for arguments shape, scale and size when good_fit is True
    parser.add_argument(
        "--shape",
        type=float,
        default=1.0,
        help="Shape parameter for generating good fit data",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=300,
        help="Scale parameter for generating good fit data",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=30,
        help="Number of samples to generate for good fit data",
    )
    parser.add_argument(
        "--poor_fit",
        type=bool,
        default=False,
        required=False,
        help="Poor fit (default: False)",
    )
    args = parser.parse_args()

    if args.good_fit:
        failure_times = stats.weibull_min.rvs(
            c=args.shape, scale=args.scale, size=args.size, random_state=42
        )
        failure_times = np.ceil(failure_times).astype(
            int
        )  # Round up to nearest integer
    elif args.poor_fit:
        # Generate two sets of data with different scales to simulate multi-modal distribution
        # Group 1: Failures that happen early (shorter failure times)
        group_1 = stats.weibull_min.rvs(
            c=1.5, scale=100, size=30, random_state=42
        )  # Weibull with a shape parameter less than 2

        # Group 2: Failures that happen later (longer failure times)
        group_2 = stats.weibull_min.rvs(
            c=5, scale=50, size=30, random_state=42
        )  # Weibull with a shape parameter greater than 2

        # Combine the two groups to create a multi-modal distribution
        failure_times = np.concatenate([group_1, group_2])
        failure_times = np.ceil(failure_times).astype(
            int
        )  # Round up to nearest integer
    elif args.failure_data:
        failure_times = np.array(args.failure_data)
    else:
        # display help message
        parser.print_help()
        sys.exit(1)

    print("=" * 60)
    print("Weibull Distribution Analysis")
    print("=" * 60)
    print(f"Number of failures: {len(failure_times)}")
    print(f"Failure times: {np.sort(failure_times)}")

    # Create plot
    # fig, beta, eta, mtbf = plot_weibull_analysis(failure_times, "Life Data Analysis")
    params = plot_weibull_analysis(failure_times, "Life Data Analysis")

    print("Estimated Weibull Parameters:")
    print(f"  Shape (β): {params['beta']:.3f}")
    print(f"  Scale (η): {params['eta']:.2f}")
    # MTBF=η⋅Γ(1+1/β​)
    mean_weibull = params['eta'] * gamma(1 + 1 / params['beta'])
    print(f"  Mean Time Between Failures (Weibull): {mean_weibull:.2f}")

    # Interpretation
    print("Interpretation:")
    if params['beta'] < 1:
        print("  β < 1: Decreasing failure rate (infant mortality)")
    elif abs(params['beta'] - 1) < 0.1:
        print("  β ≈ 1: Constant failure rate (random failures)")
    else:
        print("  β > 1: Increasing failure rate (wear-out)")

    print(f"  63.2% of failures occur by time η = {params['eta']:.2f}")
    print(f"  The B-10 life: {calculate_b_life(beta=params['beta'], eta=params['eta'], percentage=10)} hours")
    print(f"  The B-10 life: {calculate_b_life(beta=params['beta'], eta=params['eta'], percentage=20)} hours")
    print()
    print("=" * 60)
    plt.show()
