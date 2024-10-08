from importlib import metadata as importlib_metadata
from typing import Any

from shortuuid import uuid

from inspect_ai._util.constants import PKG_NAME
from inspect_ai._util.datetime import iso_now
from inspect_ai._util.git import git_context
from inspect_ai._util.path import cwd_relative_path
from inspect_ai._util.registry import (
    registry_log_name,
    registry_params,
)
from inspect_ai.dataset import Dataset
from inspect_ai.log import (
    EvalConfig,
    EvalDataset,
    EvalError,
    EvalLog,
    EvalPlan,
    EvalPlanStep,
    EvalResults,
    EvalRevision,
    EvalSample,
    EvalSpec,
    EvalStats,
)
from inspect_ai.log._log import Recorder
from inspect_ai.model import (
    GenerateConfig,
    Model,
    ModelName,
)
from inspect_ai.model._model import model_usage
from inspect_ai.solver._plan import Plan
from inspect_ai.solver._solver import Solver, SolverSpec


class TaskLogger:
    def __init__(
        self,
        task_name: str,
        task_version: int,
        task_file: str | None,
        task_id: str | None,
        run_id: str,
        solver: SolverSpec | None,
        model: Model,
        dataset: Dataset,
        sandbox: tuple[str, str | None] | None,
        task_attribs: dict[str, Any],
        task_args: dict[str, Any],
        model_args: dict[str, Any],
        eval_config: EvalConfig,
        metadata: dict[str, Any] | None,
        recorder: Recorder,
    ) -> None:
        # determine versions
        git = git_context()
        revision = (
            EvalRevision(type="git", origin=git.origin, commit=git.commit)
            if git
            else None
        )
        packages = {PKG_NAME: importlib_metadata.version(PKG_NAME)}

        # remove api_key from model_args
        model_args = model_args.copy()
        if "api_key" in model_args:
            del model_args["api_key"]

        # create eval spec
        self.eval = EvalSpec(
            run_id=run_id,
            created=iso_now(),
            task=f"{task_name}",
            task_id=task_id if task_id else uuid(),
            task_version=task_version,
            task_file=task_file,
            task_attribs=task_attribs,
            task_args=task_args,
            solver=solver.solver if solver else None,
            solver_args=solver.args if solver else None,
            model=str(ModelName(model)),
            model_base_url=model.api.base_url,
            dataset=EvalDataset(
                name=dataset.name,
                location=cwd_relative_path(dataset.location),
                samples=len(dataset),
                shuffled=dataset.shuffled,
            ),
            sandbox=sandbox,
            model_args=model_args,
            config=eval_config,
            revision=revision,
            packages=packages,
            metadata=metadata,
        )

        # stack recorder and location
        self.recorder = recorder
        self._location = self.recorder.log_start(self.eval)

        # number of samples logged
        self._samples_completed = 0

    @property
    def location(self) -> str:
        return self._location

    @property
    def samples_completed(self) -> int:
        return self._samples_completed

    def log_sample(self, sample: EvalSample, flush: bool) -> None:
        # log the sample
        self.recorder.log_sample(self.eval, sample, flush=flush)

        # track sucessful samples logged
        if sample.error is None:
            self._samples_completed += 1

    def log_plan(self, plan: EvalPlan) -> None:
        self.recorder.log_plan(self.eval, plan)

    def log_results(self, results: EvalResults) -> None:
        self.recorder.log_results(self.eval, results)

    def log_cancelled(self, stats: EvalStats) -> EvalLog:
        return self.recorder.log_cancelled(self.eval, stats)

    def log_success(self, stats: EvalStats) -> EvalLog:
        return self.recorder.log_success(self.eval, stats)

    def log_failure(self, stats: EvalStats, error: EvalError) -> EvalLog:
        return self.recorder.log_failure(self.eval, stats, error)


def log_plan(
    logger: TaskLogger,
    plan: Plan,
    config: GenerateConfig,
) -> None:
    def eval_plan_step(solver: Solver) -> EvalPlanStep:
        return EvalPlanStep(
            solver=registry_log_name(solver), params=registry_params(solver)
        )

    eval_plan = EvalPlan(
        name=plan.name,
        steps=[eval_plan_step(solver) for solver in plan.steps],
        finish=eval_plan_step(plan.finish) if plan.finish else None,
        config=config,
    )
    if plan.finish:
        eval_plan.steps.append(eval_plan_step(plan.finish))

    logger.log_plan(eval_plan)


def collect_eval_data(stats: EvalStats) -> None:
    # collect stats
    stats.completed_at = iso_now()
    stats.model_usage = model_usage()
