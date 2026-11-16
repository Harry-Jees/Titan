import unittest

from training.experience_lab import (
    ToyBalanceEnvironment,
    classify_failure,
    no_op_action,
    pd_balance_action,
    run_episode,
    score_transition,
)


class ExperienceLabTests(unittest.TestCase):
    def test_prediction_is_pure_and_matches_unforced_step(self):
        env = ToyBalanceEnvironment(initial_angle=0.12, initial_velocity=-0.03)
        before = env.observe()
        predicted = env.predict(1)
        self.assertEqual(env.observe(), before)

        transition = env.step(1)
        self.assertEqual(transition["observation"], predicted)
        self.assertFalse(transition["terminated"])

    def test_environment_rejects_unbounded_actions_and_disturbances(self):
        env = ToyBalanceEnvironment()
        with self.assertRaises(ValueError):
            env.step(2)
        with self.assertRaises(ValueError):
            env.step(0, disturbance=3.0)

    def test_pd_baseline_beats_no_op_on_held_out_initial_states(self):
        held_out = [(-0.2, 0.0), (-0.1, 0.05), (0.1, 0.0), (0.15, 0.1), (0.2, 0.0)]
        for angle, velocity in held_out:
            controlled = run_episode(
                initial_angle=angle,
                initial_velocity=velocity,
                controller=pd_balance_action,
            )
            uncontrolled = run_episode(
                initial_angle=angle,
                initial_velocity=velocity,
                controller=no_op_action,
            )
            self.assertTrue(controlled["metrics"]["success"])
            self.assertGreater(controlled["metrics"]["steps"], uncontrolled["metrics"]["steps"])

    def test_prediction_score_uses_mean_absolute_error(self):
        score = score_transition(
            {"angle": 0.1, "angular_velocity": 0.2},
            {"angle": 0.2, "angular_velocity": 0.0},
        )
        self.assertAlmostEqual(score["angle_absolute_error"], 0.1)
        self.assertAlmostEqual(score["angular_velocity_absolute_error"], 0.2)
        self.assertAlmostEqual(score["mean_absolute_error"], 0.15)

    def test_failure_classifier_uses_evidence_priority(self):
        self.assertEqual(classify_failure(
            prediction_error=0.0, safety_violation=True,
        ), "unsafe_action")
        self.assertEqual(classify_failure(
            prediction_error=0.2, observation_confidence=0.2,
        ), "perception_error")
        self.assertEqual(classify_failure(
            prediction_error=0.2, requested_action=1, applied_action=0,
        ), "actuator_failure")
        self.assertEqual(classify_failure(
            prediction_error=0.0, external_disturbance=0.2,
        ), "external_disturbance")
        self.assertEqual(classify_failure(
            prediction_error=0.2,
        ), "model_error")
        self.assertEqual(classify_failure(
            prediction_error=0.0,
        ), "planning_error")
        self.assertIsNone(classify_failure(
            prediction_error=0.0, success=True,
        ))

    def test_episode_emits_ordered_typed_events_and_metrics(self):
        result = run_episode(initial_angle=0.2, episode_id="toy-test-0001")
        self.assertEqual(result["episode"]["mode"], "simulation")
        self.assertTrue(result["metrics"]["success"])
        self.assertGreater(result["metrics"]["steps"], 0)
        self.assertEqual(result["events"][-1]["type"], "episode_ended")
        self.assertEqual(result["events"][0]["type"], "observation")
        event_types = {event["type"] for event in result["events"]}
        self.assertTrue({
            "observation", "prediction", "action_proposed",
            "action_validated", "outcome", "episode_ended",
        }.issubset(event_types))
        proposed = next(event for event in result["events"] if event["type"] == "action_proposed")
        self.assertEqual(proposed["payload"]["mode"], "simulation")


if __name__ == "__main__":
    unittest.main()
