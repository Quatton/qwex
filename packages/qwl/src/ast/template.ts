import consola from "consola";
import { Template } from "nunjucks";

import type { TaskDef, VariableDef } from "./ast";

import { nj } from "../utils/templating";

export function createTemplate(str: string): Template {
  return new Template(str, nj);
}

export function createTemplateRecord(value: VariableDef): VariableTemplateValue {
  if (typeof value === "string") return createTemplate(value);
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value))
    return value.map((item) => createTemplateRecord(item as VariableDef));
  if (typeof value === "object" && value !== null) {
    const record: Record<string, VariableTemplateValue> = {};
    for (const [key, v] of Object.entries(value)) {
      record[key] = createTemplateRecord(v as VariableDef);
    }
    return record;
  }
  return value as VariableTemplateValue;
}

export type VariableTemplateValue =
  | string
  | Template
  | number
  | boolean
  | VariableTemplateValue[]
  | { [key: string]: VariableTemplateValue };

export type VariableTemplate = {
  value: VariableTemplateValue;
  __meta__: {
    sourcePath?: string;
  };
};

export type TaskTemplate = Omit<TaskDef, "cmd" | "vars"> & {
  cmd: Template;
  vars: Record<string, VariableTemplate>;
  __meta__: {
    sourcePath?: string;
  };
};

export type ModuleTemplate = {
  __meta__: {
    used: Set<string>;
    sourcePath?: string;
  };
  vars: Record<string, VariableTemplate>;
  tasks: Record<string, TaskTemplate>;
  modules: Record<string, ModuleTemplate>;
};

export function resolveTaskDefs(
  taskDefs: Record<string, TaskDef> | undefined,
  sourcePath?: string,
) {
  const tasks: Record<string, TaskTemplate> = {};
  if (!taskDefs) {
    return tasks;
  }
  for (const [taskName, taskDef] of Object.entries(taskDefs)) {
    if (taskName.match(/-/)) {
      consola.warn(
        `Task name "${taskName}" contains a hyphen (-). Consider using underscores (_) instead to avoid potential issues or make sure to use vars['bracket-syntax'] to address such symbols.. (i.e. hyphenated-task-name will be interpreted as subtraction in some contexts)`,
      );
    }

    const cmdStr = taskDef.cmd
      ? Array.isArray(taskDef.cmd)
        ? taskDef.cmd.join("\n")
        : taskDef.cmd
      : "";
    tasks[taskName] = {
      cmd: createTemplate(cmdStr),
      vars: resolveVariableDefs(taskDef.vars, sourcePath),
      desc: taskDef.desc,
      uses: taskDef.uses,
      __meta__: { sourcePath },
    };
  }
  return tasks;
}

export function resolveVariableDefs(
  varDefs: Record<string, unknown> | undefined,
  sourcePath?: string,
) {
  const vars: Record<string, VariableTemplate> = {};
  if (!varDefs) {
    return vars;
  }
  for (const [varName, varDef] of Object.entries(varDefs)) {
    if (varName.match(/-/)) {
      consola.warn(
        `Variable name "${varName}" contains a hyphen (-). Consider using underscores (_) instead to avoid potential issues or make sure to use vars['bracket-syntax'] to address such symbols.. (i.e. hyphenated-var-name will be interpreted as subtraction in some contexts)`,
      );
    }

    vars[varName] = {
      value: createTemplateRecord(varDef as VariableDef),
      __meta__: { sourcePath },
    };
  }
  return vars;
}

export function createEmptyModuleTemplate(): ModuleTemplate {
  return {
    vars: {},
    tasks: {},
    modules: {},
    __meta__: {
      used: new Set<string>(),
    },
  };
}
