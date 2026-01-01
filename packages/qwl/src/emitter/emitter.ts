import type { RenderResult } from "../renderer";
import nunjucks from "nunjucks";
import scriptTemplate from "./script.sh.njk" with { type: "text" };

export interface EmitResult {
  script: string;
  taskCount: number;
}

export class Emitter {
  private template: nunjucks.Template;

  constructor() {
    const env = new nunjucks.Environment(null, {
      autoescape: false,
      trimBlocks: true,
      lstripBlocks: true,
    });
    this.template = new nunjucks.Template(scriptTemplate, env);
  }

  emit(result: RenderResult): EmitResult {
    const script = this.template.render({
      main: result.main,
      deps: result.deps,
    });

    return {
      script,
      taskCount: result.main.length + result.deps.length,
    };
  }
}
