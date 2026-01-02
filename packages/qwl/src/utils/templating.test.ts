import { describe, expect, it } from "bun:test";

import { nj } from "./templating";

describe("templating utils", () => {
  it("prints DEBUG env variable", () => {
    const before = Bun.env.DEBUG;
    process.env.DEBUG = "OverriddenDebugValueForTesting";
    const template = `QWEX_PREAMBLE="set -euo{{ "x" if env.DEBUG }} pipefail
shopt -s expand_aliases
{{ "export DEBUG=1" if env.DEBUG else "" }}
ORIGINAL_PWD=\\$(pwd)"`;
    const rendered = nj.renderString(template, {});
    expect(rendered).toBe(`QWEX_PREAMBLE="set -euox pipefail
shopt -s expand_aliases
export DEBUG=1
ORIGINAL_PWD=\\$(pwd)"`);
    process.env.DEBUG = before;
  });
});
