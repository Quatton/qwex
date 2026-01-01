import {
  createEmptyModuleTemplate,
  resolveVariableDefs,
  resolveTaskDefs,
  type ModuleDef,
  type ModuleTemplate,
} from "../ast";
import { QwlError } from "../errors";

export type ModuleLoader = (
  path: string,
  parentPath?: string
) => Promise<{ module: ModuleDef; hash: bigint; resolvedPath: string }>;

export class Resolver {
  private cache = new Map<bigint, ModuleTemplate>();
  private stack = new Set<bigint>();

  constructor(private loader: ModuleLoader) {}

  async resolve(path: string, parentPath?: string): Promise<ModuleTemplate> {
    const { module, hash, resolvedPath } = await this.loader(path, parentPath);

    if (this.cache.has(hash)) return this.cache.get(hash)!;
    if (this.stack.has(hash))
      throw new QwlError({
        code: "RESOLVER_ERROR",
        message: `Circular module dependency detected for module at path: ${resolvedPath}`,
      });

    this.stack.add(hash);

    try {
      const template = await this.createTemplateFromDef(module, resolvedPath);
      this.cache.set(hash, template);
      return template;
    } finally {
      this.stack.delete(hash);
    }
  }

  private async createTemplateFromDef(
    def: ModuleDef,
    currentPath: string
  ): Promise<ModuleTemplate> {
    const template = def.uses
      ? await this.resolveBase(def.uses, currentPath)
      : createEmptyModuleTemplate();

    if (def.vars) Object.assign(template.vars, resolveVariableDefs(def.vars));
    if (def.tasks) Object.assign(template.tasks, resolveTaskDefs(def.tasks));
    if (def.modules)
      await this.resolveInlineModules(template.modules, def.modules, currentPath);

    return template;
  }

  private async resolveBase(uses: string, currentPath: string): Promise<ModuleTemplate> {
    const parent = await this.resolve(uses, currentPath);
    return {
      vars: { ...parent.vars },
      tasks: { ...parent.tasks },
      modules: { ...parent.modules },
      __meta__: { used: new Set(parent.__meta__.used).add(uses) },
    };
  }

  private async resolveInlineModules(
    target: Record<string, ModuleTemplate>,
    modules: Record<string, ModuleDef>,
    currentPath: string
  ): Promise<void> {
    for (const [name, def] of Object.entries(modules)) {
      target[name] = await this.createTemplateFromDef(def, currentPath);
    }
  }
}

if (import.meta.main) {
  const { hash } = await import("../utils/hash");
  
  const module: ModuleDef = {
    uses: "base",
    vars: {
      greeting: "Hello",
      target: "{{ vars.greeting }}, World!",
      things: [
        "{{ vars.greeting }}",
        "{{ vars.greeting }} again",
        "{{ vars.greeting }} {{ vars.target }}",
      ],
    },
    tasks: {
      sayHello: {
        cmd: 'echo "{{ vars.target }}"',
        desc: "Says hello to the target",
      },
      callingSayHello: {
        cmd: 'echo "About to say hello"; {{ tasks.sayHello }}',
      },
    },
  };
  const baseModule: ModuleDef = {
    vars: {
      greeting: "Hi",
      you: "there",
    },
    tasks: {
      baseTask: {
        cmd: 'echo "This is the base task"',
      },
    },
  };
  const getModuleFromPath = async (path: string, _parent?: string) => {
    switch (path) {
      case "root":
        return {
          module,
          hash: hash(JSON.stringify(module)),
          resolvedPath: path,
        };
      case "base":
        return {
          module: baseModule,
          hash: hash(JSON.stringify(baseModule)),
          resolvedPath: path,
        };
      default:
        throw new Error(`Unknown module path: ${path}`);
    }
  };
  const resolver = new Resolver(getModuleFromPath);

  const resolved = await resolver.resolve("root");

  console.dir(
    // @ts-ignore
    Object.entries(resolved.vars).map(([k, v]) => [k, v.tmplStr]),
    { depth: null }
  );
}
