import { Loader, isBuiltin, resolveModulePath } from "../loader";
import { Parser, type ParseResult } from "../parser";
import { Resolver } from "../resolver";
import { Renderer } from "../renderer";
import { Emitter, type EmitResult } from "../emitter";
import { QwlError } from "../errors";

export interface PipelineOptions {
  entryPath: string;
}

export class Pipeline {
  private loader = new Loader();
  private parser = new Parser();

  constructor(private options: PipelineOptions) {}

  async run(): Promise<EmitResult> {
    const entryPath = await resolveModulePath(this.options.entryPath);

    const resolver = new Resolver(async (specifier, parentPath) => {
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
    });

    const template = await resolver.resolve(entryPath);
    const renderer = new Renderer();
    const result = renderer.renderAllTasks(template);
    const emitter = new Emitter();
    return emitter.emit(result);
  }
}
