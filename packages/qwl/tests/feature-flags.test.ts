import { describe, expect, it } from "bun:test";
import { resolve } from "node:path";

import { Pipeline } from "../src/pipeline/pipeline";

describe("Feature flags integration", () => {
  it("tasks[feature] overrides tasks when feature enabled", async () => {
    const sourcePath = resolve(import.meta.dir, "fixtures/feature-flag-test.yaml");

    // Without feature flag
    const pipeline1 = new Pipeline({ sourcePath });
    const result1 = await pipeline1.run();
    expect(result1.script).toContain("echo 'default task'");
    expect(result1.script).not.toContain("echo 'docker task'");

    // With docker feature flag
    const pipeline2 = new Pipeline({ sourcePath, features: ["docker"] });
    const result2 = await pipeline2.run();
    expect(result2.script).not.toContain("echo 'default task'");
    expect(result2.script).toContain("echo 'docker task'");
  });
});
