import { ModuleDef } from "../ast";
import { hash } from "../utils/hash";
import { ArkErrors } from "arktype";
import { QwlError } from "../errors";

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
  validated: Map<bigint, ModuleDef> = new Map();

  parse(content: string): ModuleDef | QwlError {
    const contentHash = hash(content);
    let cached = this.validated.get(contentHash);
    if (!cached) {
      const parsed = parseConfig(content);
      if (parsed instanceof QwlError) {
        return parsed;
      }
      cached = parsed;
      this.validated.set(contentHash, cached);
    }

    return cached;
  }
}
