import {
  createEmptyModuleTemplate,
  resolveVariableDefs,
  resolveTaskDefs,
  type ModuleDef,
  type ModuleTemplate,
} from "../ast";
import { QwlError } from "../errors";
import { hash } from "../utils/hash";

// Loader must return the resolved absolute path to serve as the 'parent' for subsequent loads
export type ModuleLoader = (
  path: string,
  parentPath?: string
) => {
  module: ModuleDef;
  hash: bigint;
  resolvedPath: string;
};

export class Resolver {
  private cache = new Map<bigint, ModuleTemplate>();
  private stack = new Set<bigint>();

  constructor(private loader: ModuleLoader) {}

  public resolve(path: string, parentPath?: string): ModuleTemplate {
    const { module, hash, resolvedPath } = this.loader(path, parentPath);

    if (this.cache.has(hash)) return this.cache.get(hash)!;
    if (this.stack.has(hash))
      throw new QwlError({
        code: "RESOLVER_ERROR",
        message: `Circular module dependency detected for module at path: ${resolvedPath}`,
      });

    this.stack.add(hash);

    try {
      const template = this.createTemplateFromDef(module, resolvedPath);
      this.cache.set(hash, template);
      return template;
    } finally {
      this.stack.delete(hash);
    }
  }

  private createTemplateFromDef(
    def: ModuleDef,
    currentPath: string
  ): ModuleTemplate {
    const template = def.uses
      ? this.resolveBase(def.uses, currentPath)
      : createEmptyModuleTemplate();

    if (def.vars) Object.assign(template.vars, resolveVariableDefs(def.vars));
    if (def.tasks) Object.assign(template.tasks, resolveTaskDefs(def.tasks));
    if (def.modules)
      this.resolveInlineModules(template.modules, def.modules, currentPath);

    return template;
  }

  private resolveBase(uses: string, currentPath: string): ModuleTemplate {
    const parent = this.resolve(uses, currentPath);
    return {
      vars: { ...parent.vars },
      tasks: { ...parent.tasks },
      modules: { ...parent.modules },
      __meta__: { used: new Set(parent.__meta__.used).add(uses) },
    };
  }

  private resolveInlineModules(
    target: Record<string, ModuleTemplate>,
    modules: Record<string, ModuleDef>,
    currentPath: string
  ) {
    for (const [name, def] of Object.entries(modules)) {
      target[name] = this.createTemplateFromDef(def, currentPath);
    }
  }
}

if (import.meta.main) {
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
  const getModuleFromPath = (path: string, parent?: string) => {
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

  const resolved = resolver.resolve("root");

  console.dir(
    // @ts-ignore
    Object.entries(resolved.vars).map(([k, v]) => [k, v.tmplStr]),
    { depth: null }
  );
}
