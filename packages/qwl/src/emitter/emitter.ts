import nunjucks from "nunjucks";

import type { RenderResult } from "../renderer";

import { nj } from "../utils/templating";
import scriptTemplate from "./script.sh.njk" with { type: "text" };

export interface EmitResult {
  script: string;
  count: number;
}

export class Emitter {
  private template: nunjucks.Template;

  constructor(templateStr?: string) {
    this.template = new nunjucks.Template(templateStr ?? scriptTemplate, nj);
  }

  emit(result: RenderResult): EmitResult {
    const tasks = [...result.deps, ...result.main];
    const script = this.template.render({
      tasks,
      main: result.main,
      deps: result.deps,
    });

    return {
      script,
      count: tasks.length,
    };
  }
}
