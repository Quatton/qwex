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
