from __future__ import annotations

import math
import statistics
from collections import deque
from typing import Final


class EtaEstimator:
    """
    Robust ETA estimator for a finite number of steps.

    Main ideas:
    - Damped Holt smoothing (level + trend)
    - No hardcoded min/max duration bounds
    - Robust outlier handling using rolling median + MAD
    - Lightweight uncertainty estimate from smoothed prediction error

    Notes:
    - `update(last_step_seconds)` must be called once per completed step
    - Outliers are not clamped; they are downweighted
    - A tiny positive floor is used only to avoid impossible negative durations
    """

    def __init__(
        self,
        total_steps: int,
        *,
        initial_step_seconds: float | None = None,
        level_weight: float = 0.25,
        trend_weight: float = 0.08,
        error_weight: float = 0.15,
        damping: float = 0.90,
        robust_window_size: int = 9,
        min_history_for_robust: int = 5,
        outlier_z_soft: float = 2.5,
        outlier_z_hard: float = 4.0,
        outlier_alpha_min_factor: float = 0.20,
    ) -> None:
        if total_steps <= 0:
            raise ValueError("total_steps must be greater than zero.")

        self.total_steps: Final[int] = total_steps
        self.level_weight: Final[float] = self._validate_open_unit_interval(
            "level_weight", level_weight
        )
        self.trend_weight: Final[float] = self._validate_open_unit_interval(
            "trend_weight", trend_weight
        )
        self.error_weight: Final[float] = self._validate_open_unit_interval(
            "error_weight", error_weight
        )
        self.damping: Final[float] = self._validate_closed_unit_interval_exclusive_zero(
            "damping", damping
        )

        if robust_window_size < 3:
            raise ValueError("robust_window_size must be at least 3.")
        if min_history_for_robust < 3:
            raise ValueError("min_history_for_robust must be at least 3.")
        if min_history_for_robust > robust_window_size:
            raise ValueError(
                "min_history_for_robust cannot be greater than robust_window_size."
            )
        if outlier_z_soft <= 0 or outlier_z_hard <= 0:
            raise ValueError("outlier z-thresholds must be greater than zero.")
        if outlier_z_soft >= outlier_z_hard:
            raise ValueError("outlier_z_soft must be smaller than outlier_z_hard.")
        if not (0.0 < outlier_alpha_min_factor <= 1.0):
            raise ValueError("outlier_alpha_min_factor must be in (0, 1].")

        self.robust_window_size: Final[int] = robust_window_size
        self.min_history_for_robust: Final[int] = min_history_for_robust
        self.outlier_z_soft: Final[float] = outlier_z_soft
        self.outlier_z_hard: Final[float] = outlier_z_hard
        self.outlier_alpha_min_factor: Final[float] = outlier_alpha_min_factor

        self.completed_steps: int = 0
        self.elapsed_seconds: float = 0.0

        self._level: float | None = (
            float(initial_step_seconds) if initial_step_seconds is not None else None
        )
        self._trend: float = 0.0
        self._eta_seconds: float = 0.0

        # Numerical safeguard only; this is not a domain bound.
        self._tiny_positive_floor: Final[float] = 1e-6

        # Rolling recent durations for robust stats.
        self._recent_durations: deque[float] = deque(maxlen=robust_window_size)

        # Start with a mild uncertainty prior if we do not know anything yet.
        initial_error_stddev = (
            float(initial_step_seconds) * 0.15
            if initial_step_seconds is not None and initial_step_seconds > 0
            else 5.0
        )
        self._error_variance: float = initial_error_stddev * initial_error_stddev

        self.last_observed_step_seconds: float | None = None
        self.last_predicted_step_seconds: float | None = None
        self.last_effective_level_weight: float | None = None
        self.last_robust_zscore: float | None = None
        self.last_median_seconds: float | None = None
        self.last_mad_seconds: float | None = None

        if initial_step_seconds is not None:
            self._eta_seconds = float(initial_step_seconds) * total_steps

    @staticmethod
    def _validate_open_unit_interval(name: str, value: float) -> float:
        if not (0.0 < value < 1.0):
            raise ValueError(f"{name} must be in the interval (0, 1).")
        return float(value)

    @staticmethod
    def _validate_closed_unit_interval_exclusive_zero(name: str, value: float) -> float:
        if not (0.0 < value <= 1.0):
            raise ValueError(f"{name} must be in the interval (0, 1].")
        return float(value)

    @property
    def remaining_steps(self) -> int:
        return self.total_steps - self.completed_steps

    @property
    def eta_seconds(self) -> float:
        return self._eta_seconds

    @property
    def percent_complete(self) -> float:
        return 100.0 * self.completed_steps / self.total_steps

    @property
    def progress_fraction(self) -> float:
        return self.completed_steps / self.total_steps

    @property
    def estimated_total_seconds(self) -> float:
        return self.elapsed_seconds + self.eta_seconds

    @property
    def eta_stddev_seconds(self) -> float:
        return math.sqrt(max(0.0, self.remaining_steps * self._error_variance))

    @property
    def eta_low_seconds(self) -> float:
        return max(0.0, self.eta_seconds - 1.3 * self.eta_stddev_seconds)

    @property
    def eta_high_seconds(self) -> float:
        return self.eta_seconds + 1.3 * self.eta_stddev_seconds

    def update(self, last_step_seconds: float) -> float:
        """
        Update the estimator with the duration of the most recently completed step.

        Returns the updated ETA in seconds.
        """
        if self.completed_steps >= self.total_steps:
            raise RuntimeError("All steps were already completed.")

        if last_step_seconds <= 0:
            raise ValueError("last_step_seconds must be greater than zero.")

        observed = float(last_step_seconds)

        # First observation initializes the state cleanly.
        if self._level is None:
            self._level = observed
            self._trend = 0.0
            self.completed_steps = 1
            self.elapsed_seconds = observed
            self._recent_durations.append(observed)
            self.last_observed_step_seconds = observed
            self.last_predicted_step_seconds = observed
            self.last_effective_level_weight = self.level_weight
            self.last_robust_zscore = 0.0
            self.last_median_seconds = observed
            self.last_mad_seconds = 0.0
            self._eta_seconds = self._forecast_remaining_seconds()
            return self._eta_seconds

        predicted = max(
            self._tiny_positive_floor,
            self._level + self.damping * self._trend,
        )

        effective_alpha, robust_z, median_recent, mad_scaled = self._effective_level_weight(
            observed
        )

        previous_level = self._level
        previous_trend = self._trend

        new_level = effective_alpha * observed + (1.0 - effective_alpha) * predicted
        new_level = max(self._tiny_positive_floor, new_level)

        new_trend = (
            self.trend_weight * (new_level - previous_level)
            + (1.0 - self.trend_weight) * self.damping * previous_trend
        )

        prediction_error = observed - predicted
        self._error_variance = (
            self.error_weight * (prediction_error ** 2)
            + (1.0 - self.error_weight) * self._error_variance
        )

        self._level = new_level
        self._trend = new_trend

        self.completed_steps += 1
        self.elapsed_seconds += observed
        self._recent_durations.append(observed)

        self.last_observed_step_seconds = observed
        self.last_predicted_step_seconds = predicted
        self.last_effective_level_weight = effective_alpha
        self.last_robust_zscore = robust_z
        self.last_median_seconds = median_recent
        self.last_mad_seconds = mad_scaled

        self._eta_seconds = self._forecast_remaining_seconds()
        return self._eta_seconds

    def _effective_level_weight(
        self, observed_duration: float
    ) -> tuple[float, float, float | None, float | None]:
        """
        Compute a robust effective alpha for the level update.

        The farther the observation is from the recent robust center,
        the less influence it gets.
        """
        if len(self._recent_durations) < self.min_history_for_robust:
            return self.level_weight, 0.0, None, None

        recent = list(self._recent_durations)
        median_recent = statistics.median(recent)

        absolute_deviations = [abs(x - median_recent) for x in recent]
        raw_mad = statistics.median(absolute_deviations)

        # Scale MAD to be comparable to stddev under a Gaussian assumption.
        mad_scaled = 1.4826 * raw_mad

        # Avoid unstable division when the history is too flat.
        robust_scale_floor = max(self._tiny_positive_floor, 0.05 * median_recent)
        robust_scale = max(mad_scaled, robust_scale_floor)

        robust_z = (observed_duration - median_recent) / robust_scale
        abs_z = abs(robust_z)

        if abs_z <= self.outlier_z_soft:
            return self.level_weight, robust_z, median_recent, mad_scaled

        if abs_z >= self.outlier_z_hard:
            alpha = self.level_weight * self.outlier_alpha_min_factor
            return alpha, robust_z, median_recent, mad_scaled

        # Smooth interpolation between soft and hard zones.
        position = (abs_z - self.outlier_z_soft) / (
            self.outlier_z_hard - self.outlier_z_soft
        )
        min_alpha = self.level_weight * self.outlier_alpha_min_factor
        alpha = self.level_weight - position * (self.level_weight - min_alpha)

        return alpha, robust_z, median_recent, mad_scaled

    def _forecast_remaining_seconds(self) -> float:
        """
        Forecast the remaining time using damped trend extrapolation.

        Forecast for m steps ahead:
            level + trend * (damping + damping^2 + ... + damping^m)

        This avoids runaway extrapolation while staying more realistic than
        a flat average.
        """
        if self.remaining_steps <= 0:
            return 0.0

        if self._level is None:
            return 0.0

        total = 0.0
        damping_power = self.damping
        damping_sum = 0.0

        for _ in range(self.remaining_steps):
            damping_sum += damping_power
            forecast = self._level + self._trend * damping_sum
            forecast = max(self._tiny_positive_floor, forecast)
            total += forecast
            damping_power *= self.damping

        return total

    def snapshot(self) -> dict[str, float | int | None]:
        return {
            "total_steps": self.total_steps,
            "completed_steps": self.completed_steps,
            "remaining_steps": self.remaining_steps,
            "elapsed_seconds": self.elapsed_seconds,
            "eta_seconds": self.eta_seconds,
            "eta_low_seconds": self.eta_low_seconds,
            "eta_high_seconds": self.eta_high_seconds,
            "eta_stddev_seconds": self.eta_stddev_seconds,
            "estimated_total_seconds": self.estimated_total_seconds,
            "percent_complete": self.percent_complete,
            "last_observed_step_seconds": self.last_observed_step_seconds,
            "last_predicted_step_seconds": self.last_predicted_step_seconds,
            "last_effective_level_weight": self.last_effective_level_weight,
            "last_robust_zscore": self.last_robust_zscore,
            "last_median_seconds": self.last_median_seconds,
            "last_mad_seconds": self.last_mad_seconds,
            "smoothed_level_seconds": self._level,
            "smoothed_trend_seconds_per_step": self._trend,
            "damping": self.damping,
        }

    @staticmethod
    def format_seconds(total_seconds: float) -> str:
        total_seconds = max(0.0, total_seconds)
        rounded = int(round(total_seconds))
        hours, remainder = divmod(rounded, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes:02d}m {seconds:02d}s"
        if minutes > 0:
            return f"{minutes}m {seconds:02d}s"
        return f"{seconds}s"