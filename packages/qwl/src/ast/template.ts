import { match } from "arktype";
import { Template } from "nunjucks";
import type { TaskDef, VariableDef } from "./ast";
import { nj } from "../utils/templating";

export function createTemplate(str: string): Template {
  const t = new Template(str, nj);
  return t;
}

export const createTemplateRecord = match({
  string: (v) => createTemplate(v),
  "string[]": (v) => v.map((item) => createTemplate(item)),
  "Record<string, string>": (v) => {
    const record: Record<string, Template> = {};
    for (const [key, value] of Object.entries(v)) {
      record[key] = createTemplate(value);
    }
    return record;
  },
  "Record<string, string>[]": (v) => {
    return v.map((item) => {
      const record: Record<string, Template> = {};
      for (const [key, value] of Object.entries(item)) {
        record[key] = createTemplateRecord(value);
      }
      return record;
    });
  },
  default: "assert",
});

export type VariableTemplate = ReturnType<typeof createTemplateRecord>;
export type TaskTemplate = Omit<TaskDef, "cmd" | "vars"> & {
  cmd: Template;
  vars: Record<string, VariableTemplate>;
};
export type ModuleTemplate = {
  __meta__: {
    used: Set<string>;
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
      vars: resolveVariableDefs(taskDef.vars ?? {}),
      desc: taskDef.desc,
    };
  }
  return tasks;
}

export function resolveVariableDefs(
  varDefs: Record<string, VariableDef> | undefined
) {
  const vars: Record<string, VariableTemplate> = {};
  if (!varDefs) {
    return vars;
  }
  for (const [varName, varDef] of Object.entries(varDefs)) {
    vars[varName] = createTemplateRecord(varDef);
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
