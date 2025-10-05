import { OpenAPIGenerator } from "@orpc/openapi";
import { ZodToJsonSchemaConverter } from "@orpc/zod/zod4";
import { APP_NAME, VERSION } from "@roam/consts";
import { contract } from ".";

const openAPIGenerator = new OpenAPIGenerator({
  schemaConverters: [
    new ZodToJsonSchemaConverter(), // <-- if you use Zod
  ],
});

export const spec = await openAPIGenerator.generate(contract, {
  info: {
    title: APP_NAME,
    version: VERSION,
  },
});

if (require.main === module) {
  const fs = await import("fs/promises");
  await fs.writeFile("openapi.json", JSON.stringify(spec, null, 2), "utf-8");
  console.log("OpenAPI spec written to openapi.json");
}
