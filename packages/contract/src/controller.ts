import { oc } from "@orpc/contract";
import z from "zod/v4";

export const controllerContract = {
  health: oc
    .$route({
      method: "GET",
      description: "Health check",
    })
    .output(z.object({ status: z.literal("ok") })),
};
