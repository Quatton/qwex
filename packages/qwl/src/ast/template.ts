import { Template } from "nunjucks";

import type { TaskDef, VariableDef } from "./ast";

import { nj } from "../utils/templating";

export function createTemplate(str: string): Template {
  return new Template(str, nj);
}

export function createTemplateRecord(value: VariableDef): VariableTemplate {
  if (typeof value === "string") return createTemplate(value);
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (Array.isArray(value)) return value.map((item) => createTemplateRecord(item as VariableDef));
  if (typeof value === "object" && value !== null) {
    const record: Record<string, VariableTemplate> = {};
    for (const [key, v] of Object.entries(value)) {
      record[key] = createTemplateRecord(v as VariableDef);
    }
    return record;
  }
  return value as VariableTemplate;
}

export type VariableTemplate =
  | Template
  | number
  | boolean
  | VariableTemplate[]
  | { [key: string]: VariableTemplate };

export type TaskTemplate = Omit<TaskDef, "cmd" | "vars"> & {
  cmd: Template;
  vars: Record<string, VariableTemplate>;
};
export type ModuleTemplate = {
  __meta__: {
    used: Set<string>;
    sourcePath?: string; // Absolute path to the source file for uses()
  };
  vars: Record<string, VariableTemplate>;
  tasks: Record<string, TaskTemplate>;
  modules: Record<string, ModuleTemplate>;
};

export function resolveTaskDefs(taskDefs: Record<string, TaskDef> | undefined) {
  const tasks: Record<string, TaskTemplate> = {};
  if (!taskDefs) {
    return tasks;
  }
  for (const [taskName, taskDef] of Object.entries(taskDefs)) {
    tasks[taskName] = {
      cmd: createTemplate(taskDef.cmd),
      vars: resolveVariableDefs(taskDef.vars),
      desc: taskDef.desc,
    };
  }
  return tasks;
}

export function resolveVariableDefs(varDefs: Record<string, unknown> | undefined) {
  const vars: Record<string, VariableTemplate> = {};
  if (!varDefs) {
    return vars;
  }
  for (const [varName, varDef] of Object.entries(varDefs)) {
    vars[varName] = createTemplateRecord(varDef as VariableDef);
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
