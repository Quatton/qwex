import { scope, type } from "arktype";

type _VariableDef = string | number | boolean | _VariableDef[] | { [key: string]: _VariableDef };

const $ = scope({
  // anything that is not a valid python identifier
  ValidKey: /^(?!\d-)[A-Za-z_]\w*$/,
  VariableDef:
    "string | number | boolean | unknown[] | Record<ValidKey, unknown>" as type.cast<_VariableDef>,
  TaskDef: {
    "cmd?": "string | string[]",
    "uses?": "string",
    "desc?": "string",
    "vars?": "Record<ValidKey, VariableDef>",
  },
  PartialModuleDef: {
    "uses?": "string",
    "vars?": "Record<ValidKey, VariableDef>",
    "tasks?": "Record<ValidKey, TaskDef>",
  },
  ModuleDef: {
    "...": "PartialModuleDef",
    "modules?": "Record<ValidKey, PartialModuleDef>",
  },
});

const types = $.export();

export const TaskDef = types.TaskDef;
export const VariableDef = types.VariableDef;
export const ModuleDef = types.ModuleDef;

export type TaskDef = typeof TaskDef.infer;
export type VariableDef = typeof VariableDef.infer;
export type ModuleDef = typeof ModuleDef.infer;
