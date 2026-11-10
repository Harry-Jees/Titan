"""Deterministic toy balance environment for Titan's Stage A learning loop.

This module uses only the Python standard library. It runs entirely in a
local simulation and never connects to tools, hardware, or external services.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

ActionController = Callable[[Mapping[str, float | int]], int]


@dataclass(frozen=True, slots=True)
class BalanceState:
    angle: float
    angular_velocity: float
    step: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "angle": self.angle,
            "angular_velocity": self.angular_velocity,
            "step": self.step,
        }


class ToyBalanceEnvironment:
    """A deterministic, bounded one-dimensional inverted-pendulum simulation."""

    environment_id = "toy-balance"

    def __init__(
        self,
        initial_angle: float = 0.2,
        initial_velocity: float = 0.0,
        *,
        time_step: float = 0.02,
        max_steps: int = 400,
        max_angle: float = 0.5,
    ) -> None:
        values = (initial_angle, initial_velocity, time_step, max_angle)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Initial state and environment limits must be finite.")
        if time_step <= 0 or max_steps < 1 or max_angle <= 0:
            raise ValueError("time_step and max_angle must be positive; max_steps must be at least one.")
        if abs(initial_angle) >= max_angle:
            raise ValueError("Initial angle must be inside the failure boundary.")
        self.time_step = time_step
        self.max_steps = max_steps
        self.max_angle = max_angle
        self.state = BalanceState(initial_angle, initial_velocity, 0)

    @staticmethod
    def _validate_action(action: int) -> None:
        if type(action) is not int or action not in (-1, 0, 1):
            raise ValueError("Torque action must be -1, 0, or 1.")

    def observe(self) -> dict[str, float | int]:
        return self.state.to_dict()

    def _transition(self, action: int, disturbance: float = 0.0) -> BalanceState:
        self._validate_action(action)
        if not math.isfinite(disturbance) or abs(disturbance) > 2.0:
            raise ValueError("Disturbance must be finite and bounded to +/-2.0.")
        acceleration = (
            9.81 * math.sin(self.state.angle)
            - 2.5 * action
            - 0.15 * self.state.angular_velocity
            + disturbance
        )
        velocity = self.state.angular_velocity + acceleration * self.time_step
        angle = self.state.angle + velocity * self.time_step
        return BalanceState(angle, velocity, self.state.step + 1)

    def predict(self, action: int) -> dict[str, float | int]:
        """Predict the next state without mutating the environment."""
        return self._transition(action).to_dict()

    def step(self, action: int, *, disturbance: float = 0.0) -> dict[str, Any]:
        """Apply one simulation-only action and return the measured transition."""
        self.state = self._transition(action, disturbance)
        terminated = abs(self.state.angle) >= self.max_angle
        truncated = self.state.step >= self.max_steps and not terminated
        reward = (
            1.0
            - min(1.0, abs(self.state.angle) / self.max_angle)
            - 0.02 * abs(self.state.angular_velocity)
        )
        return {
            "observation": self.observe(),
            "reward": reward,
            "terminated": terminated,
            "truncated": truncated,
            "applied_action": action,
        }


def pd_balance_action(state: Mapping[str, float | int]) -> int:
    """Small deterministic proportional-derivative baseline controller."""
    signal = float(state["angle"]) + 0.4 * float(state["angular_velocity"])
    if signal > 1e-4:
        return 1
    if signal < -1e-4:
        return -1
    return 0


def no_op_action(_state: Mapping[str, float | int]) -> int:
    """Uncontrolled baseline used to measure whether the controller helps."""
    return 0


def score_transition(
    predicted: Mapping[str, float | int],
    observed: Mapping[str, float | int],
) -> dict[str, float]:
    """Compare predicted and observed angle/velocity using absolute error."""
    fields = ("angle", "angular_velocity")
    errors: dict[str, float] = {}
    for field in fields:
        expected = float(predicted[field])
        actual = float(observed[field])
        if not math.isfinite(expected) or not math.isfinite(actual):
            raise ValueError("Transition values must be finite.")
        errors[field + "_absolute_error"] = abs(expected - actual)
    errors["mean_absolute_error"] = sum(errors.values()) / len(fields)
    return errors


def classify_failure(
    *,
    prediction_error: float,
    observation_confidence: float = 1.0,
    requested_action: int = 0,
    applied_action: int = 0,
    external_disturbance: float = 0.0,
    safety_violation: bool = False,
    success: bool = False,
    model_error_threshold: float = 0.05,
) -> str | None:
    """Return the highest-priority evidence-backed failure category."""
    values = (prediction_error, observation_confidence, external_disturbance, model_error_threshold)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Failure-classification measurements must be finite.")
    if not 0 <= observation_confidence <= 1 or model_error_threshold < 0:
        raise ValueError("Confidence must be in [0, 1] and threshold cannot be negative.")
    if success:
        return None
    if safety_violation:
        return "unsafe_action"
    if observation_confidence < 0.5:
        return "perception_error"
    if requested_action != applied_action:
        return "actuator_failure"
    if abs(external_disturbance) > 1e-6:
        return "external_disturbance"
    if prediction_error > model_error_threshold:
        return "model_error"
    return "planning_error"


def run_episode(
    *,
    initial_angle: float = 0.2,
    initial_velocity: float = 0.0,
    max_steps: int = 400,
    controller: ActionController = pd_balance_action,
    episode_id: str = "toy-balance-demo-0001",
) -> dict[str, Any]:
    """Run one deterministic episode and emit API-compatible typed event records."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", episode_id):
        raise ValueError("episode_id must be 8–80 letters, numbers, underscores, or hyphens.")

    env = ToyBalanceEnvironment(
        initial_angle=initial_angle,
        initial_velocity=initial_velocity,
        max_steps=max_steps,
    )
    episode = {
        "id": episode_id,
        "environmentId": env.environment_id,
        "goal": "Keep the pole balanced for the full trial",
        "mode": "simulation",
    }
    events: list[dict[str, Any]] = []
    total_reward = 0.0
    prediction_errors: list[float] = []
    failure_category: str | None = None
    terminated = False
    truncated = False

    for step_number in range(1, max_steps + 1):
        observation = env.observe()
        action = controller(observation)
        predicted = env.predict(action)
        action_id = f"step_{step_number:04d}"
        transition = env.step(action)
        measured = transition["observation"]
        score = score_transition(predicted, measured)
        prediction_errors.append(score["mean_absolute_error"])
        total_reward += float(transition["reward"])

        events.append({
            "type": "observation",
            "payload": {
                "source": env.environment_id,
                "state": observation,
                "confidence": 1.0,
            },
        })
        events.append({
            "type": "prediction",
            "payload": {
                "actionId": action_id,
                "expected": {
                    "angle": predicted["angle"],
                    "angular_velocity": predicted["angular_velocity"],
                },
                "uncertainty": 0.0,
            },
        })
        events.append({
            "type": "action_proposed",
            "payload": {
                "actionId": action_id,
                "name": "apply_torque",
                "parameters": {"torque": action},
                "mode": "simulation",
            },
        })
        events.append({
            "type": "action_validated",
            "payload": {
                "actionId": action_id,
                "approved": True,
                "reason": "Torque is inside the toy simulator's discrete action bounds.",
            },
        })
        events.append({
            "type": "outcome",
            "payload": {
                "actionId": action_id,
                "observed": measured,
                "success": not transition["terminated"],
                "reward": float(transition["reward"]),
                "error": score["mean_absolute_error"],
            },
        })

        terminated = bool(transition["terminated"])
        truncated = bool(transition["truncated"])
        if terminated or truncated:
            if terminated:
                failure_category = classify_failure(
                    prediction_error=score["mean_absolute_error"],
                    requested_action=action,
                    applied_action=int(transition["applied_action"]),
                    success=False,
                )
                if failure_category:
                    events.append({
                        "type": "diagnosis",
                        "payload": {
                            "category": failure_category,
                            "explanation": "The simulated pole crossed the balance boundary.",
                            "evidence": [
                                "final observed angle",
                                "final transition prediction error",
                            ],
                        },
                    })
            break

    success = not terminated
    steps = env.state.step
    events.append({
        "type": "episode_ended",
        "payload": {
            "summary": f"Completed {steps} steps with total reward {total_reward:.3f}.",
            "success": success,
        },
    })
    return {
        "episode": episode,
        "events": events,
        "metrics": {
            "steps": steps,
            "success": success,
            "terminated": terminated,
            "truncated": truncated,
            "total_reward": total_reward,
            "mean_prediction_error": (
                sum(prediction_errors) / len(prediction_errors) if prediction_errors else 0.0
            ),
            "max_prediction_error": max(prediction_errors, default=0.0),
            "failure_category": failure_category,
        },
    }


def _json_lines(result: Mapping[str, Any]) -> str:
    rows = [{"record": "episode", **result["episode"]}]
    rows.extend({"record": "event", **event} for event in result["events"])
    rows.append({"record": "metrics", **result["metrics"]})
    return "\n".join(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Titan's deterministic toy balance episode.")
    parser.add_argument("--initial-angle", type=float, default=0.2)
    parser.add_argument("--initial-velocity", type=float, default=0.0)
    parser.add_argument("--max-steps", type=int, default=400)
    parser.add_argument("--episode-id", default="toy-balance-demo-0001")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    result = run_episode(
        initial_angle=args.initial_angle,
        initial_velocity=args.initial_velocity,
        max_steps=args.max_steps,
        episode_id=args.episode_id,
    )
    output = _json_lines(result)
    if args.output:
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
