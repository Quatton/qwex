import { Emitter, type EmitResult } from "../emitter";
import { QwlError } from "../errors";
import { Loader, resolveModulePath } from "../loader";
import { Parser } from "../parser";
import { Renderer } from "../renderer";
import { Resolver } from "../resolver";

export interface PipelineOptions {
  entryPath: string;
  features?: string[];
}

export class Pipeline {
  private loader = new Loader();
  private parser = new Parser();

  constructor(private options: PipelineOptions) {}

  async run(): Promise<EmitResult> {
    const entryPath = await resolveModulePath(this.options.entryPath);
    const features = new Set(this.options.features ?? []);

    const resolver = new Resolver(
      async (specifier, parentPath) => {
        const resolvedPath = await resolveModulePath(specifier, parentPath);
        const text = await this.loader.load(resolvedPath);
        const parsed = this.parser.parse(text);
        if (parsed instanceof QwlError) {
          throw parsed;
        }
        return {
          module: parsed.module,
          hash: parsed.hash,
          resolvedPath,
        };
      },
      { features },
    );

    const template = await resolver.resolve(entryPath);
    const renderer = new Renderer();
    const result = renderer.renderAllTasks(template);
    const emitter = new Emitter();
    return emitter.emit(result);
  }
}
