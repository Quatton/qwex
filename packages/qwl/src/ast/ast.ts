import { scope } from "arktype";

const $ = scope({
  VariableDef:
    "string | string[] | Record<string, string> | Record<string, string>[]",
  TaskDef: {
    cmd: "string",
    "desc?": "string",
    "vars?": "Record<string, VariableDef>",
  },
  PartialModuleDef: {
    "uses?": "string",
    "vars?": "Record<string, VariableDef>",
    "tasks?": "Record<string, TaskDef>",
  },
  ModuleDef: {
    "...": "PartialModuleDef",
    "modules?": "Record<string, PartialModuleDef>",
  },
});

const types = $.export();

export const TaskDef = types.TaskDef;
export const VariableDef = types.VariableDef;
export const ModuleDef = types.ModuleDef;

export type TaskDef = typeof TaskDef.infer;
export type VariableDef = typeof VariableDef.infer;
export type ModuleDef = typeof ModuleDef.infer;
