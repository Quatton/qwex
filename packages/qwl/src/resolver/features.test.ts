import { describe, expect, it } from "bun:test";

import { filterByFeatures, parseFeatureKey, selectUses } from "./features";

describe("parseFeatureKey", () => {
  it("parses plain keys", () => {
    expect(parseFeatureKey("foo")).toEqual({ base: "foo", feature: null });
  });

  it("parses feature keys", () => {
    expect(parseFeatureKey("foo[bar]")).toEqual({ base: "foo", feature: "bar" });
  });

  it("parses nested brackets as plain key", () => {
    // Nested brackets are not valid feature keys - treated as plain key
    expect(parseFeatureKey("foo[bar[baz]]")).toEqual({
      base: "foo[bar[baz]]",
      feature: null,
    });
  });
});

describe("filterByFeatures", () => {
  it("returns empty object for undefined", () => {
    expect(filterByFeatures(undefined, new Set())).toEqual({});
  });

  it("returns all plain keys when no features enabled", () => {
    const record = { a: 1, b: 2 };
    expect(filterByFeatures(record, new Set())).toEqual({ a: 1, b: 2 });
  });

  it("excludes feature keys when feature not enabled", () => {
    const record = { a: 1, "b[ssh]": 2 };
    expect(filterByFeatures(record, new Set())).toEqual({ a: 1 });
  });

  it("includes feature keys when feature enabled", () => {
    const record = { a: 1, "b[ssh]": 2 };
    expect(filterByFeatures(record, new Set(["ssh"]))).toEqual({ a: 1, b: 2 });
  });

  it("feature key overrides plain key", () => {
    const record = { a: 1, "a[ssh]": 2 };
    expect(filterByFeatures(record, new Set(["ssh"]))).toEqual({ a: 2 });
  });

  it("plain key used when feature not enabled", () => {
    const record = { a: 1, "a[ssh]": 2 };
    expect(filterByFeatures(record, new Set())).toEqual({ a: 1 });
  });

  it("handles multiple features", () => {
    const record = { "a[ssh]": 1, "b[docker]": 2, c: 3 };
    expect(filterByFeatures(record, new Set(["ssh"]))).toEqual({ a: 1, c: 3 });
    expect(filterByFeatures(record, new Set(["docker"]))).toEqual({ b: 2, c: 3 });
    expect(filterByFeatures(record, new Set(["ssh", "docker"]))).toEqual({
      a: 1,
      b: 2,
      c: 3,
    });
  });
});

describe("selectUses", () => {
  it("returns undefined when no uses", () => {
    expect(selectUses({}, new Set())).toBeUndefined();
  });

  it("returns plain uses", () => {
    expect(selectUses({ uses: "./base.yaml" }, new Set())).toBe("./base.yaml");
  });

  it("returns feature uses when enabled", () => {
    expect(
      selectUses({ uses: "./base.yaml", "uses[ssh]": "./ssh-base.yaml" }, new Set(["ssh"])),
    ).toBe("./ssh-base.yaml");
  });

  it("returns plain uses when feature not enabled", () => {
    expect(selectUses({ uses: "./base.yaml", "uses[ssh]": "./ssh-base.yaml" }, new Set())).toBe(
      "./base.yaml",
    );
  });

  it("feature uses overrides plain uses", () => {
    expect(
      selectUses(
        { uses: "./base.yaml", "uses[docker]": "./docker-base.yaml" },
        new Set(["docker"]),
      ),
    ).toBe("./docker-base.yaml");
  });
});
