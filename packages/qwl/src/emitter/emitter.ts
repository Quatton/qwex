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
