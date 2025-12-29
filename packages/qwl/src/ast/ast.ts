import { type } from "arktype";

export const Variable = type("string | Record<string, string>");

export type Variable = typeof Variable.infer;

export const Task = type({
  "desc?": "string",
  cmd: "string",
});

export type Task = typeof Task.infer;

export const Config = type({
  vars: {
    "[string]": Variable,
  },
  tasks: {
    "[string]": Task,
  },
});

export type Config = typeof Config.infer;
