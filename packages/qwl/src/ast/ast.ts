import { scope, type } from "arktype";

type _VariableDef = string | number | boolean | _VariableDef[] | { [key: string]: _VariableDef };

const $ = scope({
  VariableDef:
    "string | number | boolean | unknown[] | Record<string, unknown>" as type.cast<_VariableDef>,
  TaskDef: {
    cmd: "string",
    "desc?": "string",
    "vars?": "Record<string, VariableDef>",
  },
  // Allow any string keys (including feature flags like "uses[ssh]")
  PartialModuleDef: "Record<string, unknown>",
  ModuleDef: "Record<string, unknown>",
});

const types = $.export();

export const TaskDef = types.TaskDef;
export const VariableDef = types.VariableDef;
export const ModuleDef = types.ModuleDef;

export type TaskDef = {
  cmd: string;
  desc?: string;
  vars?: Record<string, unknown>;
};

export type VariableDef = typeof VariableDef.infer;

export type ModuleDef = {
  uses?: string;
  vars?: Record<string, unknown>;
  tasks?: Record<string, TaskDef>;
  modules?: Record<string, ModuleDef>;
  // Allow any other keys for feature flags
  [key: string]: unknown;
};
