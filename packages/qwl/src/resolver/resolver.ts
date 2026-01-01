import consola from "consola";

import {
  createEmptyModuleTemplate,
  resolveTaskDefs,
  resolveVariableDefs,
  type ModuleDef,
  type ModuleTemplate,
  type TaskDef,
} from "../ast";
import { QwlError } from "../errors";
import { filterByFeatures, selectUses } from "./features";

export type ModuleLoader = (
  path: string,
  parentPath?: string,
) => Promise<{ module: ModuleDef; hash: bigint; resolvedPath: string }>;

export interface ResolverOptions {
  features?: Set<string>;
}

export class Resolver {
  private cache = new Map<bigint, ModuleTemplate>();
  private stack = new Set<bigint>();
  private features: Set<string>;

  constructor(
    private loader: ModuleLoader,
    options: ResolverOptions = {},
  ) {
    this.features = options.features ?? new Set();
  }

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
    currentPath: string,
  ): Promise<ModuleTemplate> {
    // Select uses based on feature flags
    const uses = selectUses(def as Record<string, unknown>, this.features);

    const template = uses ? await this.resolveBase(uses, currentPath) : createEmptyModuleTemplate();

    // Set source path for uses() function
    template.__meta__.sourcePath = currentPath;

    const vars = filterByFeatures(def.vars as Record<string, unknown> | undefined, this.features);
    Object.assign(template.vars, resolveVariableDefs(vars, currentPath));

    const tasks = filterByFeatures(def.tasks as Record<string, TaskDef> | undefined, this.features);
    Object.assign(template.tasks, resolveTaskDefs(tasks, currentPath));

    // Filter modules by features
    const modules = filterByFeatures(
      def.modules as Record<string, ModuleDef> | undefined,
      this.features,
    );
    if (Object.keys(modules).length > 0) {
      await this.resolveInlineModules(template.modules, modules, currentPath);
    }

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
    currentPath: string,
  ): Promise<void> {
    for (const [name, def] of Object.entries(modules)) {
      if (name.match(/-/)) {
        consola.warn(
          `Module name "${name}" contains a hyphen (-). Consider using underscores (_) instead to avoid potential issues or make sure to use vars['bracket-syntax'] to address such symbols.. (i.e. hyphenated-module-name will be interpreted as subtraction in some contexts)`,
        );
      }

      target[name] = await this.createTemplateFromDef(def, currentPath);
    }
  }
}
