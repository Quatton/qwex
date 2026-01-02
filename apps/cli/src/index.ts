import { defineCommand, runMain } from "citty";
import { consola } from "consola";
import { spawn } from "node:child_process";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { Pipeline, QwlError } from "qwl";

consola.options = {
  ...consola.options,
  stdout: process.stderr,
};

const main = defineCommand({
  meta: {
    name: "qwex",
    version: "0.1.0",
    description: "QWEX - YAML-based task runner",
  },
  args: {
    features: {
      type: "string",
      alias: "f",
      description: "Feature flags (comma-separated)",
    },
    config: {
      type: "string",
      alias: "c",
      default: "qwex.yaml",
      description: "Path to config file",
    },
    output: {
      type: "string",
      alias: "o",
      description: "Output file path",
    },
    envFile: {
      type: "string",
      alias: "e",
      description: "Path to .env file",
    },
  },
  async run({ args }) {
    if (Bun.env.DEBUG) {
      consola.info("Compiled with DEBUG mode enabled");
    }

    const configPath = resolve(args.config);
    const features = args.features ? args.features.split(",") : undefined;

    const bashArgs = args._;

    try {
      const pipeline = new Pipeline({
        sourcePath: configPath,
        features,
      });

      const { script } = await pipeline.run();

      if (args.output !== undefined) {
        if (args.output === "") {
          process.stdout.write(script);
          process.exit(0);
        }
        await writeFile(args.output, script);
        consola.info(`Script written to ${args.output}`);
      }

      const proc = spawn("bash", ["-c", script, "--", ...bashArgs], {
        stdio: "inherit",
      });

      proc.on("exit", (code) => {
        process.exit(code ?? 0);
      });

      proc.on("error", (error) => {
        consola.error("Failed to execute script:", error.message);
        process.exit(1);
      });
    } catch (e) {
      if (!(e instanceof QwlError)) {
        consola.error(e);
        process.exit(1);
      }

      consola.error(e.message);

      switch (e instanceof QwlError ? e.code : "UNKNOWN_ERROR") {
        case "LOADER_ERROR":
          consola.error(
            "Please check the file path and ensure it exists. Qwex defaults to './qwex.yaml' in the current directory.",
          );
          break;
        default:
          break;
      }

      process.exit(1);
    }
  },
});

runMain(main);
