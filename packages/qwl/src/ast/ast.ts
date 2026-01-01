import { scope, type } from "arktype";

type _VariableDef = string | number | boolean | _VariableDef[] | { [key: string]: _VariableDef };

const $ = scope({
  "ValidRecord<t>": {
    "[/^[A-Za-z_][A-Za-z0-9_]*$/]": "t",
  },
  VariableDef:
    "string | number | boolean | unknown[] | ValidRecord<unknown>" as type.cast<_VariableDef>,
  TaskDef: {
    "cmd?": "string | string[]",
    "uses?": "string",
    "desc?": "string",
    "vars?": "ValidRecord<VariableDef>",
  },
  PartialModuleDef: {
    "uses?": "string",
    "vars?": "ValidRecord<VariableDef>",
    "tasks?": "ValidRecord<TaskDef>",
  },
  ModuleDef: {
    "...": "PartialModuleDef",
    "modules?": "ValidRecord<PartialModuleDef>",
  },
});

const types = $.export();

export const TaskDef = types.TaskDef;
export const VariableDef = types.VariableDef;
export const ModuleDef = types.ModuleDef;

export type TaskDef = typeof TaskDef.infer;
export type VariableDef = typeof VariableDef.infer;
export type ModuleDef = typeof ModuleDef.infer;
