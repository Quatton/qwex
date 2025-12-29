import { parse } from "yaml";
import { Config } from "../ast";

export function parseConfig(content: string) {
  const config = parse(content);
  return Config(config);
}
