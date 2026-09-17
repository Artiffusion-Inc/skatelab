import { z } from "zod"
import { defineDocs, defineCollections, defineConfig } from "fumadocs-mdx/config"

// ponytail: defineDocs default dir is 'content/docs', defineCollections needs explicit dir.
// No `param`/`baseUrl` options in fumadocs-mdx@15 — route params live in app router, not collections.
export const docs = defineDocs({
  dir: "content/docs",
})

export const blog = defineCollections({
  type: "doc",
  dir: "content/blog",
  schema: z.object({
    title: z.string(),
    description: z.string(),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    image: z.enum(["recording-guide", "training-notes", "blade-macro", "coach-review"]),
  }),
})

export default defineConfig()
