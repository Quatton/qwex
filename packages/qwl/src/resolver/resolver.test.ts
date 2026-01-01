import { describe, expect, test } from "bun:test";
import { strict as assert } from "node:assert";

import { type ModuleDef } from "../ast";
import { hash } from "../utils/hash";
import { Resolver, type ModuleLoader } from "./resolver";

const createLoader = (modules: Record<string, ModuleDef>): ModuleLoader => {
  return async (path: string) => {
    const module = modules[path];
    if (!module) throw new Error(`Module not found: ${path}`);
    return {
      module,
      hash: hash(JSON.stringify(module)),
      resolvedPath: path,
    };
  };
};

describe("Resolver", () => {
  test("1. resolve vars and tasks normally", async () => {
    const modules = {
      root: {
        vars: { v1: "val1" },
        tasks: { t1: { cmd: "echo {{ vars.v1 }}" } },
      },
    };
    const resolver = new Resolver(createLoader(modules));
    const result = await resolver.resolve("root");

    expect(result.vars.v1).toBeDefined();
    // @ts-ignore
    expect(result.vars.v1.tmplStr).toBe("val1");
    expect(result.tasks.t1).toBeDefined();
    // @ts-ignore
    expect(result.tasks.t1?.cmd.tmplStr).toBe("echo {{ vars.v1 }}");
  });

  test("2. resolve inline modules normally", async () => {
    const modules = {
      root: {
        modules: {
          child1: { vars: { c1: "childVal1" } },
          child2: { vars: { c2: "childVal2" } },
        },
      },
    };
    const resolver = new Resolver(createLoader(modules));
    const result = await resolver.resolve("root");

    expect(result.modules.child1).toBeDefined();
    // @ts-ignore
    expect(result.modules.child1.vars.c1.tmplStr).toBe("childVal1");
    expect(result.modules.child2).toBeDefined();
    // @ts-ignore
    expect(result.modules.child2.vars.c2.tmplStr).toBe("childVal2");
  });

  test("3. resolve uses (inheritance)", async () => {
    const modules = {
      base: {
        vars: { shared: "baseVal", overrideMe: "base" },
      },
      root: {
        uses: "base",
        vars: { overrideMe: "root" },
      },
    };
    const resolver = new Resolver(createLoader(modules));
    const result = await resolver.resolve("root");

    // @ts-ignore
    expect(result.vars.shared.tmplStr).toBe("baseVal");
    // @ts-ignore
    expect(result.vars.overrideMe.tmplStr).toBe("root");
    expect(result.__meta__.used.has("base")).toBe(true);
  });

  test("4. resolve uses in inline modules", async () => {
    const modules = {
      common: {
        vars: { key: "commonKey" },
      },
      root: {
        modules: {
          sub: {
            uses: "common",
            vars: { subKey: "subVal" },
          },
        },
      },
    };
    const resolver = new Resolver(createLoader(modules));
    const result = await resolver.resolve("root");

    const sub = result.modules.sub;
    assert(sub, "Expected sub module to be defined");
    // @ts-ignore
    expect(sub.vars.key.tmplStr).toBe("commonKey");
    // @ts-ignore
    expect(sub.vars.subKey.tmplStr).toBe("subVal");
    expect(sub.__meta__.used.has("common")).toBe(true);
  });

  test("5. prevent cyclic dependency (direct)", async () => {
    const modules = {
      a: { uses: "b" },
      b: { uses: "a" },
    };
    const resolver = new Resolver(createLoader(modules));

    await expect(resolver.resolve("a")).rejects.toThrow(/Circular module dependency/);
  });

  test("6. prevent cyclic dependency (nested/indirect)", async () => {
    const modules = {
      modA: {
        modules: {
          inlineB: { uses: "modC" },
        },
      },
      modC: {
        modules: {
          inlineD: { uses: "modA" },
        },
      },
    };
    const resolver = new Resolver(createLoader(modules));

    await expect(resolver.resolve("modA")).rejects.toThrow(/Circular module dependency/);
  });
});
