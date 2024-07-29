from dataclasses import dataclass
from logging import getLogger
from typing import Any, Callable, Sequence, cast

from pydantic import BaseModel
from typing_extensions import TypedDict, Unpack

from inspect_ai._util.registry import is_registry_object, registry_info
from inspect_ai.dataset import Dataset, MemoryDataset, Sample
from inspect_ai.log import EvalLog
from inspect_ai.model import GenerateConfig
from inspect_ai.scorer import Metric, Scorer
from inspect_ai.scorer._reducer import ScoreReducers, create_reducers
from inspect_ai.solver import Plan, Solver, generate

logger = getLogger(__name__)


class TaskDeprecatedArgs(TypedDict, total=False):
    tool_environment: str | tuple[str, str] | None


class Task:
    r"""Evaluation task.

    Tasks are the basis for defining and running evaluations. Tasks
    are parameterized with a dataset, a scorer, and metrics. Tasks
    also may optionally provide a default plan for execution.

    Args:
        dataset (Dataset | Sequence[Sample]): Dataset to evaluate
        plan: (Plan | Solver | list[Solver]): Default plan. If not specified
          defaults to generate(), a normal call to the model.
        scorer: (Scorer | list[Scorer] | None): Scorer used to evaluate model output.
        metrics (list[Metric]): Additional metrics to compute beyond
          the base metrics provided by the scorer.
        config (GenerateConfig): Model generation config.
        sandbox (str | tuple[str,str] | None): Sandbox
           environment type (or optionally a tuple with type and config file)
        epochs (int): Default number of epochs to run for.
        epochs_reducer (ScoreReducers | None):
           Reducer function(s) for aggregating scores in each sample (defaults to average).
        max_messages (int | None): Limit on total messages in the conversation.
        name: (str | None): Task name. If not specified is automatically
          determined based on the name of the task directory (or "task")
          if its anonymous task (e.g. created in a notebook and passed to
          eval() directly)
        version: (int): Version of task (to distinguish evolutions
          of the task spec or breaking changes to it)
    """

    def __init__(
        self,
        dataset: Dataset | Sequence[Sample],
        plan: Plan | Solver | list[Solver] = generate(),
        scorer: Scorer | list[Scorer] | None = None,
        metrics: list[Metric] = [],
        config: GenerateConfig = GenerateConfig(),
        sandbox: str | tuple[str, str] | None = None,
        epochs: int | None = None,
        epochs_reducer: ScoreReducers | None = None,
        max_messages: int | None = None,
        name: str | None = None,
        version: int = 0,
        **kwargs: Unpack[TaskDeprecatedArgs],
    ) -> None:
        # handle deprecated args
        for arg, value in kwargs.items():
            newarg = ""
            if arg == "tool_environment":
                newarg = "sandbox"
                sandbox = cast(str | tuple[str, str] | None, value)
            if newarg:
                logger.warning(
                    f"DEPRECATED: the '{arg}' parameter is deprecated (please use the '{newarg}' parameter instead)"
                )

        self.dataset: Dataset = (
            dataset if isinstance(dataset, Dataset) else MemoryDataset(list(dataset))
        )
        self.plan = plan if isinstance(plan, Plan) else Plan(plan)
        self.scorer = (
            scorer
            if isinstance(scorer, list)
            else [scorer]
            if scorer is not None
            else None
        )
        self.metrics = metrics
        self.config = config
        self.sandbox = (sandbox, None) if isinstance(sandbox, str) else sandbox
        self.epochs = epochs
        self.epochs_reducer = create_reducers(epochs_reducer)
        self.max_messages = max_messages
        self.version = version
        self._name = name

    @property
    def name(self) -> str:
        if self._name is not None:
            return self._name
        elif is_registry_object(self):
            return registry_info(self).name
        else:
            return "task"

    @property
    def attribs(self) -> dict[str, Any]:
        if is_registry_object(self):
            return cast(dict[str, Any], registry_info(self).metadata.get("attribs", {}))
        else:
            return dict()


class TaskInfo(BaseModel):
    """Task information (file, name, and attributes)."""

    file: str
    """File path where task was loaded from."""

    name: str
    """Task name (defaults to function name)"""

    attribs: dict[str, Any]
    """Task attributes (arguments passed to `@task`)"""

    def __str__(self) -> str:
        return f"{self.file}@{self.name}"

    def __hash__(self) -> int:
        return hash(
            (self.file, self.name)
            + tuple(self.attribs.keys())
            + tuple(self.attribs.values())
        )


@dataclass
class PreviousTask:
    id: str
    task: str
    log: EvalLog


Tasks = (
    str
    | PreviousTask
    | TaskInfo
    | Task
    | Callable[..., Task]
    | type[Task]
    | list[str]
    | list[PreviousTask]
    | list[TaskInfo]
    | list[Task]
    | list[Callable[..., Task]]
    | list[type[Task]]
    | None
)
r"""One or more tasks.

Tasks to be evaluated. Many forms of task specification are
supported including directory names, task functions, task
classes, and task instances (a single task or list of tasks
can be specified). None is a request to read a task out
of the current working directory.
"""
