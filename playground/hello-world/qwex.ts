type TaskConfig = {
  name: string;
  steps?: Array<TaskStepConfig>;
};

type TaskStepConfig = {
  name?: string;
} & (
  {
    run: string;
  } |
  {
    uses: string;
    with?: Record<string, any>;
  }
)