import argparse
import sys
import time
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from scipy import stats
from scipy.special import gamma

from weibull_fit import b_life, bootstrap_bounds, fit_weibull

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
    """Calculates the B-Life for a given percentage."""
    return int(round(b_life(beta, eta, percentage)))


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
    ax.set_xlabel("Time to failure (hours), log scale", fontsize=10)

    return prob_positions


def plot_weibull_analysis(  # noqa: PLR0915
    failure_times,
    title="Weibull Probability Plot",
    censored_times=None,
    method="rry",
    confidence=0.9,
):
    """Create Weibull probability paper with optional suspensions and bootstrap bounds."""
    fit = fit_weibull(np.asarray(failure_times, dtype=float), censored_times, method=method)
    plt.switch_backend("Agg")
    beta = fit["beta"]
    eta = fit["eta"]
    t_sorted = fit["failure_times"]
    F = fit["ranks"]
    censored = fit["censored_times"]
    _x_data, y_data = linearize_weibull(t_sorted, F)
    bounds = bootstrap_bounds(t_sorted, censored, method=fit["method"], confidence=confidence)

    plt.rcParams["font.family"] = "Arial"

    fig = plt.figure(figsize=(8.5, 11))
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

    prob_positions = create_weibull_paper(ax1, title)

    ax1.plot(
        t_sorted,
        y_data,
        "o",
        markersize=8,
        color="blue",
        label="Failures",
        markerfacecolor="lightblue",
        markeredgewidth=2,
        markeredgecolor="blue",
        zorder=5,
    )

    if len(censored):
        y_suspensions = np.log(
            np.log(1.0 / (1.0 - np.clip(weibull_cdf(censored, beta, eta), 1e-6, 1 - 1e-6)))
        )
        ax1.plot(
            censored,
            y_suspensions,
            "+",
            markersize=10,
            markeredgewidth=2,
            color="dimgray",
            label="Suspensions",
            zorder=4,
        )

    cdf_values = np.linspace(0.001, 0.999, 100)
    y_fit = np.log(-np.log(1 - cdf_values))
    x_fit = eta * ((-np.log(1 - cdf_values)) ** (1 / beta))
    ax1.plot(
        x_fit, y_fit, color="black", linestyle="-", linewidth=2.0, label="Fitted line", zorder=3
    )

    if bounds.get("available"):
        x_low = []
        x_high = []
        for cdf in cdf_values:
            xs = [
                sample_eta * ((-np.log(1 - cdf)) ** (1 / sample_beta))
                for sample_beta, sample_eta in zip(
                    bounds["samples"]["beta"], bounds["samples"]["eta"]
                )
            ]
            alpha = (1.0 - confidence) / 2.0
            x_low.append(np.percentile(xs, 100 * alpha))
            x_high.append(np.percentile(xs, 100 * (1.0 - alpha)))
        ax1.fill_betweenx(
            y_fit,
            x_low,
            x_high,
            color="steelblue",
            alpha=0.18,
            label=f"{int(confidence * 100)}% bootstrap band",
            zorder=2,
        )

    F_632 = 0.632
    y_632 = np.log(np.log(1 / (1 - F_632)))
    ax1.axhline(y=y_632, color="green", linestyle="--", linewidth=2, alpha=0.7)
    ax1.axvline(x=eta, color="green", linestyle="--", linewidth=2, alpha=0.7)
    ax1.plot(
        eta,
        y_632,
        "s",
        markersize=12,
        color="green",
        markeredgewidth=2,
        markeredgecolor="darkgreen",
        label=f"η (scale) = {eta:.2f} at 63.2%",
    )

    y_max = max(prob_positions) + 0.5
    y_min = min(prob_positions) - 0.5
    ax1.set_ylim([y_min, y_max])

    x_top = (y_max - y_632) / beta
    ax1.plot(
        np.exp([0, x_top]),
        [y_632, y_max],
        "purple",
        linewidth=2.5,
        linestyle="-.",
        label=f"β line (from (0, 63.2%)) = {beta:.3f}",
    )

    ax1_1 = ax1.twiny()
    beta_values = [0.5, 1, 2, 3, 4, 5, 8, 10]
    ax1_1.set_xlim(np.log(ax1.get_xlim()))
    ax1_1.set_xlabel(
        "Shape Parameter (β) Reference", fontsize=10, fontweight="bold", color="purple"
    )
    ax1_1.set_xscale("linear")
    beta_positions = [(y_max - y_632) / b for b in beta_values]
    ax1_1.set_xticks(beta_positions)
    ax1_1.set_xticklabels([f"{b}" for b in beta_values], color="purple", fontsize=8)
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

    mtbf_value = fit["mtbf"]
    method_label = "MLE" if fit["method"] == "mle" else "median ranks + rank regression on Y (RRY)"
    sample_label = (
        f"{fit['n_failures']} failures, {fit['n_censored']} suspensions"
        if fit["n_censored"]
        else f"{fit['n_failures']} failures only"
    )
    stats_text = "Weibull parameters\n"
    stats_text += f"Shape (β): {beta:.3f}\n"
    stats_text += f"Scale (η): {eta:.2f} hours\n"
    stats_text += f"MTBF: {mtbf_value:.2f} hours\n"
    stats_text += f"{sample_label}\n"
    stats_text += f"Method: {method_label}"
    if bounds.get("available"):
        stats_text += f"\nBounds: {int(confidence * 100)}% bootstrap"

    ax1.text(
        0.02,
        0.98,
        stats_text,
        transform=ax1.transAxes,
        fontsize=8,
        verticalalignment="top",
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.88),
    )

    ks_stat, p_value = stats.kstest(t_sorted, lambda x: stats.weibull_min.cdf(x, beta, scale=eta))
    fit_text = "Goodness of fit (failures only, informal)\n"
    fit_text += f"K-S statistic: {ks_stat:.4f}\n"
    fit_text += f"p-value: {p_value:.4f}"
    ax1.text(
        0.98,
        0.18,
        fit_text,
        transform=ax1.transAxes,
        fontsize=8,
        verticalalignment="bottom",
        horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.88),
    )

    ax1.legend(loc="lower right", fontsize=8, framealpha=0.9)

    ax2.hist(
        t_sorted,
        bins=min(8, max(3, len(t_sorted) // 2)),
        color="blue",
        edgecolor="white",
        label="Failures",
    )
    ax2.set_title("Histogram", fontsize=12, fontweight="bold", pad=5)
    ax2.set_xlabel("Time in Hours")
    ax2.set_ylabel("Frequency of Failure")
    ax2.legend()

    t_grid = np.linspace(
        max(t_sorted.min() * 0.5, 1e-6),
        max(t_sorted.max(), float(np.max(censored) if len(censored) else 0), eta),
        80,
    )
    hazard_function = stats.weibull_min.pdf(t_grid, c=beta, scale=eta) / stats.weibull_min.sf(
        t_grid, c=beta, scale=eta
    )
    ax3.plot(t_grid, hazard_function, color="black", linewidth=1.5)
    ax3.set_title("Hazard Rate (Trend)", fontsize=12, fontweight="bold", pad=5)
    ax3.set_xlabel("Time in Hours")
    ax3.set_ylabel("Hazard Function")

    plt.tight_layout()

    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    save_path = str(static_dir / f"weibull_plot_{int(time.time() * 1000)}.png")
    fig.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    payload = {
        "file": save_path,
        "beta": beta,
        "eta": eta,
        "mtbf": mtbf_value,
        "ks_stat": ks_stat,
        "p_value": p_value,
        "method": fit["method"],
        "n_failures": fit["n_failures"],
        "n_censored": fit["n_censored"],
        "b10": b_life(beta, eta, 10),
        "b20": b_life(beta, eta, 20),
        "b30": b_life(beta, eta, 30),
        "confidence": confidence,
        "message": f"Weibull plot saved as {save_path}",
    }
    if bounds.get("available"):
        payload["bounds"] = {
            "method": bounds["bound_method"],
            "confidence": bounds["confidence"],
            "beta": bounds["beta"],
            "eta": bounds["eta"],
            "b10": bounds["b10"],
            "b20": bounds["b20"],
        }
    return payload


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
        failure_times = np.ceil(failure_times).astype(int)  # Round up to nearest integer
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
        failure_times = np.ceil(failure_times).astype(int)  # Round up to nearest integer
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
    mean_weibull = params["eta"] * gamma(1 + 1 / params["beta"])
    print(f"  Mean Time Between Failures (Weibull): {mean_weibull:.2f}")

    # Interpretation
    print("Interpretation:")
    if params["beta"] < 1:
        print("  β < 1: Decreasing failure rate (infant mortality)")
    elif abs(params["beta"] - 1) < 0.1:  # noqa: PLR2004
        print("  β ≈ 1: Constant failure rate (random failures)")
    else:
        print("  β > 1: Increasing failure rate (wear-out)")

    print(f"  63.2% of failures occur by time η = {params['eta']:.2f}")
    print(
        f"  The B-10 life: {calculate_b_life(beta=params['beta'], eta=params['eta'], percentage=10)} hours"
    )
    print(
        f"  The B-20 life: {calculate_b_life(beta=params['beta'], eta=params['eta'], percentage=20)} hours"
    )
    print()
    print("=" * 60)
