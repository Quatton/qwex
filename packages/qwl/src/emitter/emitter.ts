import nunjucks from "nunjucks";

import type { RenderResult } from "../renderer";

import scriptTemplate from "./script.sh.njk" with { type: "text" };

export interface EmitResult {
  script: string;
  count: number;
}

export class Emitter {
  private template: nunjucks.Template;

  constructor(templateStr?: string) {
    const env = new nunjucks.Environment(null, {
      autoescape: false,
      trimBlocks: true,
      lstripBlocks: true,
    });

    env.addFilter("chomp", (value: unknown) => {
      if (typeof value !== "string") return value;
      // Remove exactly one trailing newline if present, but preserve intentional blank-line
      // endings ("\n\n") which are used in some fixtures.
      if (value.endsWith("\n") && !value.endsWith("\n\n")) {
        return value.slice(0, -1);
      }
      return value;
    });

    env.addFilter("chompUnlessDesc", (value: unknown, desc: unknown) => {
      // Some fixtures expect a trailing blank line for tasks with a description.
      // Keep those as-is, but chomp exactly one newline for tasks without a description.
      if (desc) return value;
      if (typeof value !== "string") return value;
      if (value.endsWith("\n") && !value.endsWith("\n\n")) {
        return value.slice(0, -1);
      }
      return value;
    });

    env.addFilter("postTaskSpacing", (desc: unknown) => {
      // Circular fixture expects a blank line between tasks when a description is present.
      return desc ? "\n" : "";
    });

    this.template = new nunjucks.Template(templateStr ?? scriptTemplate, env);
  }

  emit(result: RenderResult): EmitResult {
    const script = this.template.render({
      main: result.main,
      deps: result.deps,
    });

    return {
      script,
      count: result.main.length + result.deps.length,
    };
  }
}
