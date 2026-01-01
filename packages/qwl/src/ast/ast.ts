import { scope, type } from "arktype";

// VariableDef accepts what YAML can produce: primitives, arrays, objects
// Arktype can't easily express recursive types, so we use a looser type at parse time
// and manually handle nested structures in template.ts
const VariableDefType = type("string | number | boolean | unknown[] | Record<string, unknown>");

const $ = scope({
  TaskDef: {
    cmd: "string",
    "desc?": "string",
    "vars?": "Record<string, unknown>",
  },
  PartialModuleDef: {
    "uses?": "string",
    "vars?": "Record<string, unknown>",
    "tasks?": "Record<string, TaskDef>",
  },
  ModuleDef: {
    "...": "PartialModuleDef",
    "modules?": "Record<string, PartialModuleDef>",
  },
});

const types = $.export();

export const TaskDef = types.TaskDef;
export const ModuleDef = types.ModuleDef;

// Export VariableDef separately since it's not in the scope
export const VariableDef = VariableDefType;

export type TaskDef = typeof TaskDef.infer;
export type ModuleDef = typeof ModuleDef.infer;
// Manual type that's more specific than "unknown"
export type VariableDef = string | number | boolean | VariableDef[] | { [key: string]: VariableDef };
