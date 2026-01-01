import { ModuleDef } from "../ast";
import { hash } from "../utils/hash";
import { ArkErrors } from "arktype";
import { QwlError } from "../errors";

export interface ParseResult {
  module: ModuleDef;
  hash: bigint;
}

export function parseConfig(content: string): ModuleDef | QwlError {
  try {
    const config = Bun.YAML.parse(content);
    const res = ModuleDef(config);
    if (res instanceof ArkErrors) {
      return QwlError.from(res);
    }
    return res;
  } catch (e) {
    return QwlError.from(e);
  }
}

export class Parser {
  private cache = new Map<bigint, ModuleDef>();

  parse(content: string): ParseResult | QwlError {
    const contentHash = hash(content);
    let cached = this.cache.get(contentHash);
    if (!cached) {
      const parsed = parseConfig(content);
      if (parsed instanceof QwlError) {
        return parsed;
      }
      cached = parsed;
      this.cache.set(contentHash, cached);
    }

    return { module: cached, hash: contentHash };
  }
}
