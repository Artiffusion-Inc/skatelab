import { defineDocs, defineCollections, defineConfig } from "fumadocs-mdx/config"

// ponytail: defineDocs default dir is 'content/docs', defineCollections needs explicit dir.
// No `param`/`baseUrl` options in fumadocs-mdx@15 — route params live in app router, not collections.
export const docs = defineDocs({
  dir: "content/docs",
})

export const blog = defineCollections({
  type: "doc",
  dir: "content/blog",
})

export default defineConfig()