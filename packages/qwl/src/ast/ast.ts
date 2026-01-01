import { scope, type } from "arktype";

type _VariableDef = string | number | boolean | _VariableDef[] | { [key: string]: _VariableDef };

const $ = scope({
  VariableDef:
    "string | number | boolean | unknown[] | Record<string, unknown>" as type.cast<_VariableDef>,
  TaskDef: {
    "cmd?": "string | string[]",
    "uses?": "string",
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
